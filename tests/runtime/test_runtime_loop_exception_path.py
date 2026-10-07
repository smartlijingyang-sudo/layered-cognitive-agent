"""Regression lock for the runtime loop exception path (ADR-0183 PR-10).

Both ``except`` branches of ``CognitiveRuntime._run_driver`` normalize the
real exception instance via ``exc_to_record`` before the single emitter
(``lca.infrastructure.observability.spine.exception_emit``): the
``exception.caught`` payload carries the full ``ExceptionRecord`` field set
(``exception_class`` / ``traceback_text`` / ``call_frames`` / ``err_kind``),
and the ``CancelledError`` branch binds the live exception instead of
hand-written strings. The ``exception.finally`` / ``lifecycle.finally``
outcome split is unchanged (ADR-0166 S5).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, cast

import pytest

from lca.contracts.models.core.execution.result import Result
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.models.observability.journal.journal import RunScope
from lca.contracts.protocols.runtime.runtime.lifecycle import (
    RuntimeLifecycleEvent,
    RuntimeLifecycleEventType,
)
from lca.harness.declarative.compile.instrument.wrap import set_active_spine_accessor
from lca.infrastructure.observability.facade.run.context import run_scope
from lca.runtime.loop.runtime_loop import CognitiveRuntime
from lca.session.append import Session
from lca_kernel.events.bus.bus import EnvelopeBus


class _RecordingSpine:
    """Structural EventSpine double recording ``append`` keyword args."""

    def __init__(self) -> None:
        self.appends: list[dict[str, Any]] = []

    def append(
        self,
        *,
        execution_point: str,
        channel: str,
        caller_payload: dict[str, Any] | None = None,
        outcome: str | None = None,
    ) -> None:
        self.appends.append(
            {
                "execution_point": execution_point,
                "channel": channel,
                "payload": caller_payload,
                "outcome": outcome,
            }
        )


@pytest.fixture
def recording_spine() -> Iterator[_RecordingSpine]:
    """Install a recording spine behind the process-local accessor."""
    spine = _RecordingSpine()
    previous = set_active_spine_accessor(lambda: spine)
    try:
        yield spine
    finally:
        set_active_spine_accessor(previous)


@pytest.fixture
def sent_payloads() -> Iterator[list[Any]]:
    """Capture envelope emits routed through the default EnvelopeBus."""
    sent: list[Any] = []

    class _RecordingBus:
        def publish(self, payload: Any, *, producer: type, trace_id: str | None = None) -> None:
            sent.append(payload)

    EnvelopeBus.set_default(cast("Any", _RecordingBus()))
    try:
        yield sent
    finally:
        EnvelopeBus.set_default(None)


@pytest.fixture
def bound_session() -> Iterator[Session]:
    """Bind a real Session: Session-SSOT facts commit instead of loud-drop.

    ``exception.finally`` / ``lifecycle.finally`` (and ``exception.caught``
    when a session is bound) no longer travel the default EnvelopeBus; without
    a bound session ``publish_ep_bound`` drops them with
    ``fact_gateway.unbound_drop`` (0379).
    """
    from lca.plugins.events.publishers._session_publish import (
        reset_publish_session,
        set_publish_session,
    )

    session = Session("runtime-exception-path-test")
    token = set_publish_session(session)
    try:
        yield session
    finally:
        reset_publish_session(token)


def _session_facts(session: Session, execution_point: str) -> list[Any]:
    """Session events carrying the given spine ``execution_point``."""
    return [
        event
        for event in session.snapshot_events()
        if event.data.get("execution_point") == execution_point
    ]


@dataclass
class _RecordingSubscriber:
    events: list[RuntimeLifecycleEvent]

    async def publish(self, event: RuntimeLifecycleEvent) -> None:
        self.events.append(event)


@dataclass
class _Bindings:
    lifecycle_publisher: object

    def plan_ref(self) -> str:
        return "plan://runtime-exception-path-test"


def _runtime(events: list[RuntimeLifecycleEvent]) -> CognitiveRuntime:
    return CognitiveRuntime(cast("Any", _Bindings(_RecordingSubscriber(events))))


def _state() -> AgentState:
    return AgentState(
        trace_id="trace-driver",
        task="driver task",
        budget=Budget(max_steps=8),
    )


@pytest.mark.asyncio
async def test_driver_failure_emits_normalized_exception_record(
    bound_session: Session,
) -> None:
    events: list[RuntimeLifecycleEvent] = []
    runtime = _runtime(events)

    async def _runner() -> Result:
        raise ValueError("driver boom")

    with pytest.raises(ValueError, match="driver boom"):
        await runtime._run_driver(_state(), runner=_runner)

    caught = _session_facts(bound_session, "exception.caught")
    assert len(caught) == 1
    payload = caught[0].data["payload"]
    assert payload is not None
    assert payload["boundary"] == "terminal_driver"
    assert payload["exception_class"] == "ValueError"
    assert payload["exception_message"] == "driver boom"
    assert payload["err_kind"] == "internal"
    assert payload["trace_id"] == "trace-driver"
    assert "ValueError: driver boom" in payload["traceback_text"]
    assert payload["call_frames"], "call_frames must survive normalization"

    assert [event.type for event in events] == [RuntimeLifecycleEventType.FAILED]
    finally_events = _session_facts(bound_session, "exception.finally")
    assert len(finally_events) == 1
    assert finally_events[0].data["payload"]["outcome"] == "failure"
    assert not _session_facts(bound_session, "lifecycle.finally")


@pytest.mark.asyncio
async def test_driver_cancellation_binds_real_exception_instance(
    bound_session: Session,
) -> None:
    events: list[RuntimeLifecycleEvent] = []
    runtime = _runtime(events)

    async def _runner() -> Result:
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await runtime._run_driver(_state(), runner=_runner)

    caught = _session_facts(bound_session, "exception.caught")
    assert len(caught) == 1
    payload = caught[0].data["payload"]
    assert payload is not None
    # The live instance drives the record: qualname from its type, traceback
    # and err_kind from the instance — no hardcoded class/message strings.
    assert payload["exception_class"] == "CancelledError"
    assert payload["err_kind"] == "cancelled"
    assert payload["traceback_text"], "cancellation must keep its traceback"
    assert payload["trace_id"] == "trace-driver"

    assert [event.type for event in events] == [RuntimeLifecycleEventType.CANCELED]
    finally_events = _session_facts(bound_session, "exception.finally")
    assert len(finally_events) == 1
    assert finally_events[0].data["payload"]["outcome"] == "cancelled"


@pytest.mark.asyncio
async def test_driver_run_scope_run_id_reaches_record(
    recording_spine: _RecordingSpine,
    sent_payloads: list[Any],
) -> None:
    del sent_payloads
    runtime = _runtime([])

    async def _runner() -> Result:
        raise ValueError("scoped boom")

    scope = RunScope(trace_id="trace-driver", run_id="run-driver")
    with pytest.raises(ValueError, match="scoped boom"), run_scope(scope):
        await runtime._run_driver(_state(), runner=_runner)

    caught = [
        append
        for append in recording_spine.appends
        if append["execution_point"] == "exception.caught"
    ]
    assert len(caught) == 1
    payload = caught[0]["payload"]
    assert payload is not None
    assert payload["run_id"] == "run-driver"


@pytest.mark.asyncio
async def test_driver_success_keeps_lifecycle_finally_envelope(
    bound_session: Session,
) -> None:
    runtime = _runtime([])
    result = Result(
        trace_id="trace-driver",
        status=TaskStatus.COMPLETED,
        final_state_ref="state://driver/1",
        total_steps=1,
        budget_used=Budget(used_steps=1),
    )

    async def _runner() -> Result:
        return result

    returned = await runtime._run_driver(_state(), runner=_runner)

    assert returned is result
    assert _session_facts(bound_session, "exception.caught") == []
    lifecycle = _session_facts(bound_session, "lifecycle.finally")
    assert len(lifecycle) == 1
    assert lifecycle[0].data["payload"]["outcome"] == "success"
    assert not _session_facts(bound_session, "exception.finally")
