"""Tests for CognitiveRuntime.run() guard branches (run leg of dispatch->assemble->run).

Pins the run()-level seams that no prior test reaches:
1. ADR-0268 section 6 handoff: a non-empty ``developer_seed`` extra is appended
   as a developer message only -- no user bubble is created for the task.
2. An empty developer_seed falls back to the plain user message.
3. ``auto_review_mode`` extras flow into the per-run BindingsView; an invalid
   value falls back to "off" with no gate instead of raising.
4. ``origin`` extras override the carrier-stamped default, while an unnamed
   origin leaves the default ("user") untouched.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from lca.contracts.models.core.execution.result import Result
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.models.team.run.context import RunContext
from lca.contracts.protocols.runtime.runtime.lifecycle import (
    RuntimeLifecycleEvent,
)
from lca.infrastructure.auto_review.gate import AutoReviewGate
from lca.infrastructure.runtime_plane.capability_bindings import (
    current_bindings_view,
)
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.runtime.loop.runtime_loop import CognitiveRuntime
from lca.session.append import Session


class _RecordingSubscriber:
    def __init__(self) -> None:
        self.events: list[RuntimeLifecycleEvent] = []

    async def publish(self, event: RuntimeLifecycleEvent) -> None:
        self.events.append(event)


class _ViewCapturingDriver:
    """Driver mock that records the active BindingsView mid-run."""

    def __init__(
        self,
        captured_states: list[AgentState],
        captured_views: list[Any],
    ) -> None:
        self._states = captured_states
        self._views = captured_views

    async def run(self, state: AgentState) -> Result:
        self._states.append(state)
        # Inside with_runtime_bindings(runtime_overrides, ...), so the view
        # carries exactly what run() backfilled for this turn.
        self._views.append(current_bindings_view())
        return Result(
            trace_id=state.trace_id,
            status=TaskStatus.COMPLETED,
            final_state_ref=state.trace_id,
            total_steps=1,
            budget_used=Budget(),
            output="ok",
        )


class _Bindings:
    def __init__(
        self,
        captured_states: list[AgentState],
        captured_views: list[Any],
    ) -> None:
        self.lifecycle_publisher = _RecordingSubscriber()
        self.capabilities: dict[str, Any] = {}
        self.captured_states = captured_states
        self.captured_views = captured_views
        self.reducer = MagicMock()

    def plan_ref(self) -> str:
        return "plan://test-run-guards"

    def require_executable_plan(self) -> None:
        pass

    def with_writer(self, writer: Any) -> _Bindings:
        self.capabilities["writer"] = writer
        return self

    def new_driver(self) -> _ViewCapturingDriver:
        return _ViewCapturingDriver(self.captured_states, self.captured_views)

    def new_state(
        self,
        *,
        trace_id: str,
        task: str,
        budget: Budget,
        agent_role: str,
        from_role: str,
        team_awareness: Any,
    ) -> AgentState:
        return AgentState(
            trace_id=trace_id,
            task=task,
            budget=budget,
            agent_role=agent_role,
            from_role=from_role,
            team_awareness=team_awareness,
        )


async def _run_with_session(
    task: str,
    ctx: RunContext | None,
    session: Session,
) -> tuple[list[AgentState], list[Any]]:
    """Run one turn against a live session; return (states, mid-run views)."""
    set_publish_session(cast("Any", session))
    captured_states: list[AgentState] = []
    captured_views: list[Any] = []
    bindings = _Bindings(captured_states, captured_views)
    runtime = CognitiveRuntime(cast("Any", bindings))
    try:
        result = await runtime.run(task=task, ctx=ctx)
    finally:
        reset_publish_session(None)
    assert result.status == TaskStatus.COMPLETED
    assert len(captured_states) == 1
    assert len(captured_views) == 1
    return captured_states, captured_views


@pytest.mark.asyncio
async def test_developer_seed_appended_as_developer_message_only() -> None:
    """ADR-0268 S6: a handoff turn seeds developer content, no user bubble."""
    from lca.runtime.session.run_session_writer import RunSessionWriter

    session = Session("test-session-handoff")
    ctx = RunContext(
        trace_id="trace-handoff",
        session_id="s-handoff",
        extra={"developer_seed": "cron worker report payload", "developer_seed_job_id": "job-1"},
    )
    await _run_with_session(task="handoff task text", ctx=ctx, session=session)

    messages = RunSessionWriter(session=session).derive_messages()
    assert len(messages) == 1
    assert messages[0]["role"] == "developer"
    assert messages[0]["content"] == "cron worker report payload"
    # The task must NOT also appear as a user bubble (dedupe placeholder risk).
    assert not any(m.get("role") == "user" for m in messages)


@pytest.mark.asyncio
async def test_empty_developer_seed_falls_back_to_user_message() -> None:
    from lca.runtime.session.run_session_writer import RunSessionWriter

    session = Session("test-session-empty-seed")
    ctx = RunContext(
        trace_id="trace-empty-seed",
        session_id="s-empty-seed",
        extra={"developer_seed": ""},
    )
    await _run_with_session(task="plain task text", ctx=ctx, session=session)

    messages = RunSessionWriter(session=session).derive_messages()
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "plain task text"


@pytest.mark.asyncio
async def test_auto_review_mode_enforce_backfilled_into_bindings_view() -> None:
    session = Session("test-session-ar-enforce")
    ctx = RunContext(
        trace_id="trace-ar-enforce",
        session_id="s-ar-enforce",
        extra={"auto_review_mode": "enforce"},
    )
    _, views = await _run_with_session(task="review me", ctx=ctx, session=session)

    view = views[0]
    assert view is not None
    assert view.auto_review_mode == "enforce"
    assert isinstance(view.auto_review_gate, AutoReviewGate)


@pytest.mark.asyncio
async def test_invalid_auto_review_mode_falls_back_to_off() -> None:
    session = Session("test-session-ar-bogus")
    ctx = RunContext(
        trace_id="trace-ar-bogus",
        session_id="s-ar-bogus",
        extra={"auto_review_mode": "bogus"},
    )
    _, views = await _run_with_session(task="review me", ctx=ctx, session=session)

    view = views[0]
    assert view is not None
    assert view.auto_review_mode == "off"
    assert view.auto_review_gate is None


@pytest.mark.asyncio
async def test_ctx_origin_overrides_carrier_default() -> None:
    session = Session("test-session-origin-handoff")
    ctx = RunContext(
        trace_id="trace-origin",
        session_id="s-origin",
        extra={"origin": "handoff"},
    )
    _, views = await _run_with_session(task="handoff origin", ctx=ctx, session=session)

    view = views[0]
    assert view is not None
    assert view.origin == "handoff"


@pytest.mark.asyncio
async def test_unnamed_origin_keeps_default() -> None:
    session = Session("test-session-origin-default")
    _, views = await _run_with_session(task="plain", ctx=None, session=session)

    view = views[0]
    assert view is not None
    assert view.origin == "user"
