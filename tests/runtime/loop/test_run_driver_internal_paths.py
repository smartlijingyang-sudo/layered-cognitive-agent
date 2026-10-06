"""Pin the internal branches of ``CognitiveRuntime._run_driver`` that the
exception-path suite leaves uncovered (ADR-0183 PR-10 companion).

Covered here, at the ``_run_driver`` level (not end-to-end):
1. vocal widget branch — a gate that ``is_awaiting_widget()`` flips the
   result to ``INPUT_REQUIRED`` and pins the latest widget message into
   ``Result.extra["approval_request"]``; an idle gate leaves the result
   untouched.
2. vocal settle guard — ``validate_turn_settle()`` is invoked exactly once
   on the success path when a guard is bound (ADR-0248 hard gate).
3. resume envelope — ``resume_envelope=True`` emits ``runtime.resume.end``
   with the real outcome (``success`` / ``failure``), carrying the
   plan/node the envelope was captured with (ADR-0246 PR-3.4).
4. initiative feature derivation — when ``RunContext.extra`` carries no
   ``transcript_features``, baseline features are derived from
   ``ctx.prior_turns`` (user/assistant turn counts) before the
   initiative hook runs (ADR-0248 slice 8).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, cast

import pytest

import lca.application.initiative.hooks as initiative_hooks
from lca.application.vocal.runtime_wiring import RuntimeVocalContext
from lca.contracts.models.core.conversation.conversation import ConversationTurn
from lca.contracts.models.core.execution.result import Result
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.models.team.run.context import RunContext
from lca.contracts.models.vocal.models import VocalMode
from lca.contracts.protocols.runtime.runtime.lifecycle import RuntimeLifecycleEvent
from lca.harness.declarative.compile.instrument.wrap import set_active_spine_accessor
from lca.runtime.loop.runtime_loop import CognitiveRuntime
from lca.session.append import Session


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
    spine = _RecordingSpine()
    previous = set_active_spine_accessor(lambda: spine)
    try:
        yield spine
    finally:
        set_active_spine_accessor(previous)


@pytest.fixture
def bound_session() -> Iterator[Session]:
    from lca.plugins.events.publishers._session_publish import (
        reset_publish_session,
        set_publish_session,
    )

    session = Session("runtime-run-driver-paths-test")
    token = set_publish_session(session)
    try:
        yield session
    finally:
        reset_publish_session(token)


def _session_facts(session: Session, execution_point: str) -> list[Any]:
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
        return "plan://runtime-run-driver-paths-test"


def _runtime(events: list[RuntimeLifecycleEvent]) -> CognitiveRuntime:
    return CognitiveRuntime(cast("Any", _Bindings(_RecordingSubscriber(events))))


def _state() -> AgentState:
    return AgentState(
        trace_id="trace-run-driver",
        task="run driver task",
        budget=Budget(max_steps=8),
    )


def _result(status: TaskStatus = TaskStatus.COMPLETED) -> Result:
    return Result(
        trace_id="trace-run-driver",
        status=status,
        final_state_ref="state://run-driver/1",
        total_steps=1,
        budget_used=Budget(used_steps=1),
    )


class _FakeGate:
    """Minimal vocal gate double for the widget branch."""

    def __init__(self, awaiting: bool, visible: list[dict[str, Any]]) -> None:
        self._awaiting = awaiting
        self._visible = visible

    def is_awaiting_widget(self) -> bool:
        return self._awaiting

    def get_visible_outputs(self) -> list[dict[str, Any]]:
        return self._visible


class _RecordingSettleGuard:
    def __init__(self) -> None:
        self.calls = 0

    def validate_turn_settle(self) -> None:
        self.calls += 1


def _vocal_ctx(gate: Any, settle_guard: Any = None) -> RuntimeVocalContext:
    return RuntimeVocalContext(mode=VocalMode.GATED, gate=gate, settle_guard=settle_guard)


@pytest.mark.asyncio
async def test_widget_gate_sets_input_required_and_approval_request(
    recording_spine: _RecordingSpine, bound_session: Session
) -> None:
    events: list[RuntimeLifecycleEvent] = []
    runtime = _runtime(events)
    gate = _FakeGate(
        awaiting=True,
        visible=[
            {"type": "text", "content": "internal scratchpad"},
            {
                "type": "widget",
                "message_id": "w-old",
                "content": "旧审批",
                "options": ["a"],
            },
            {
                "type": "widget",
                "message_id": "w-latest",
                "content": "请确认执行",
                "options": ["确认", "取消"],
            },
        ],
    )

    async def _runner() -> Result:
        return _result()

    result = await runtime._run_driver(_state(), runner=_runner, vocal_ctx=_vocal_ctx(gate))

    assert result.status is TaskStatus.INPUT_REQUIRED
    assert result.extra["approval_request"] == {
        "type": "widget",
        "message_id": "w-latest",
        "content": "请确认执行",
        "options": ["确认", "取消"],
    }
    # Non-widget outputs never leak into the approval request.
    assert "scratchpad" not in str(result.extra["approval_request"])


@pytest.mark.asyncio
async def test_idle_widget_gate_keeps_result_status(
    recording_spine: _RecordingSpine, bound_session: Session
) -> None:
    events: list[RuntimeLifecycleEvent] = []
    runtime = _runtime(events)
    gate = _FakeGate(awaiting=False, visible=[])

    async def _runner() -> Result:
        return _result()

    result = await runtime._run_driver(_state(), runner=_runner, vocal_ctx=_vocal_ctx(gate))

    assert result.status is TaskStatus.COMPLETED
    assert "approval_request" not in result.extra


@pytest.mark.asyncio
async def test_settle_guard_validated_once_on_success(
    recording_spine: _RecordingSpine, bound_session: Session
) -> None:
    events: list[RuntimeLifecycleEvent] = []
    runtime = _runtime(events)
    guard = _RecordingSettleGuard()
    gate = _FakeGate(awaiting=False, visible=[])

    async def _runner() -> Result:
        return _result()

    result = await runtime._run_driver(_state(), runner=_runner, vocal_ctx=_vocal_ctx(gate, guard))

    assert result.status is TaskStatus.COMPLETED
    assert guard.calls == 1


@pytest.mark.asyncio
async def test_resume_envelope_emits_end_with_success_outcome(
    recording_spine: _RecordingSpine, bound_session: Session
) -> None:
    events: list[RuntimeLifecycleEvent] = []
    runtime = _runtime(events)

    async def _runner() -> Result:
        return _result()

    result = await runtime._run_driver(
        _state(),
        runner=_runner,
        phase_cursor="node-9",
        resume_envelope=True,
    )

    assert result.status is TaskStatus.COMPLETED
    ends = _session_facts(bound_session, "runtime.resume.end")
    assert len(ends) == 1
    payload = ends[0].data["payload"]
    assert payload["outcome"] == "success"
    assert payload["node_id"] == "node-9"
    assert payload["plan_ref"] == "plan://runtime-run-driver-paths-test"


@pytest.mark.asyncio
async def test_resume_envelope_emits_end_with_failure_outcome(
    recording_spine: _RecordingSpine, bound_session: Session
) -> None:
    events: list[RuntimeLifecycleEvent] = []
    runtime = _runtime(events)

    async def _runner() -> Result:
        raise RuntimeError("driver blew up")

    with pytest.raises(RuntimeError, match="driver blew up"):
        await runtime._run_driver(
            _state(),
            runner=_runner,
            phase_cursor="node-9",
            resume_envelope=True,
        )

    ends = _session_facts(bound_session, "runtime.resume.end")
    assert len(ends) == 1
    assert ends[0].data["payload"]["outcome"] == "failure"
    assert ends[0].data["payload"]["node_id"] == "node-9"


@pytest.mark.asyncio
async def test_initiative_features_derived_from_prior_turns(
    recording_spine: _RecordingSpine,
    bound_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[RuntimeLifecycleEvent] = []
    runtime = _runtime(events)
    captured: list[dict[str, Any]] = []

    def _spy(features: dict[str, Any]) -> None:
        captured.append(features)
        return None

    monkeypatch.setattr(initiative_hooks, "evaluate_initiative", _spy)

    ctx = RunContext(
        trace_id="trace-initiative-derive",
        session_id="s-derive",
        extra={},  # no transcript_features: derive from prior_turns
        prior_turns=(
            ConversationTurn(role="user", content="查一下天气"),
            ConversationTurn(role="assistant", content="好的"),
            ConversationTurn(role="user", content="再查一下路况"),
        ),
    )

    async def _runner() -> Result:
        return _result()

    result = await runtime._run_driver(_state(), runner=_runner, ctx=ctx)

    assert result.status is TaskStatus.COMPLETED
    assert len(captured) == 1
    assert captured[0] == {
        "user_turn_count": 2,
        "assistant_turn_count": 1,
        "manual_action_counts": {},
    }
    # Hook returned None: nothing written back into the read-only input contract.
    assert "initiative_offer" not in result.extra


@pytest.mark.asyncio
async def test_no_resume_envelope_emits_no_resume_end(
    recording_spine: _RecordingSpine, bound_session: Session
) -> None:
    events: list[RuntimeLifecycleEvent] = []
    runtime = _runtime(events)

    async def _runner() -> Result:
        return _result()

    await runtime._run_driver(_state(), runner=_runner)

    assert _session_facts(bound_session, "runtime.resume.end") == []
