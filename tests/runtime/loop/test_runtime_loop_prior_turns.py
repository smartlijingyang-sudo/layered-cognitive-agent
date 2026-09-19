"""Tests for runtime_loop prior turns injection (ADR-0244 PR-2 Task 6).

Verifies that:
1. prior_turns from RunContext are seeded via run_writer.seed_prior_turns;
2. PRIOR_CONVERSATION_WM_KEY is retired and NOT written into state.extra;
3. derive_messages() on writer includes both prior turns and the current task in chronological order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from lca.contracts.models.core.conversation.conversation import (
    PRIOR_CONVERSATION_WM_KEY,
    ConversationTurn,
)
from lca.contracts.models.core.execution.result import Result
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.models.team.run.context import RunContext
from lca.contracts.protocols.runtime.runtime.lifecycle import (
    RuntimeLifecycleEvent,
)
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.runtime.loop.runtime_loop import CognitiveRuntime
from lca.runtime.session.run_session_writer import RunSessionWriter
from lca.session.append import Session


@dataclass
class _RecordingSubscriber:
    events: list[RuntimeLifecycleEvent] = field(default_factory=list)

    async def publish(self, event: RuntimeLifecycleEvent) -> None:
        self.events.append(event)


class _MockDriver:
    def __init__(self, captured_states: list[AgentState]) -> None:
        self.captured_states = captured_states

    async def run(self, state: AgentState) -> Result:
        self.captured_states.append(state)
        return Result(
            trace_id=state.trace_id,
            status=TaskStatus.COMPLETED,
            final_state_ref=state.trace_id,
            total_steps=1,
            budget_used=Budget(),
            output="ok",
        )


class _Bindings:
    def __init__(self, captured_states: list[AgentState]) -> None:
        self.lifecycle_publisher = _RecordingSubscriber()
        self.capabilities: dict[str, Any] = {}
        self.captured_states = captured_states
        self.reducer = MagicMock()

    def plan_ref(self) -> str:
        return "plan://test-prior-turns"

    def require_executable_plan(self) -> None:
        pass

    def with_writer(self, writer: Any) -> _Bindings:
        self.capabilities["writer"] = writer
        return self

    def new_driver(self) -> _MockDriver:
        return _MockDriver(self.captured_states)

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


@pytest.mark.asyncio
async def test_runtime_loop_seeds_prior_turns_and_avoids_state_extra_key() -> None:
    session = Session("test-session-loop")
    set_publish_session(cast("Any", session))

    captured_states: list[AgentState] = []
    bindings = _Bindings(captured_states)
    runtime = CognitiveRuntime(cast("Any", bindings))

    prior_turns = (
        ConversationTurn(role="user", content="上一轮用户输入"),
        ConversationTurn(role="assistant", content="上一轮助手回复"),
    )
    ctx = RunContext(trace_id="trace-123", session_id="s1", prior_turns=prior_turns)

    try:
        result = await runtime.run(
            task="本轮任务请求",
            ctx=ctx,
        )
    finally:
        reset_publish_session(None)

    assert result.status == TaskStatus.COMPLETED
    assert len(captured_states) == 1
    state = captured_states[0]

    # Invariant C4: state.extra must NOT contain PRIOR_CONVERSATION_WM_KEY
    assert PRIOR_CONVERSATION_WM_KEY not in state.extra, (
        f"PRIOR_CONVERSATION_WM_KEY should be retired, found in state.extra: {state.extra}"
    )

    # Invariant C3: Prior turns must be seeded into Session facts
    writer = RunSessionWriter(session=session)
    messages = writer.derive_messages()
    assert len(messages) == 3
    assert messages[0] == {"role": "user", "content": "上一轮用户输入"}
    assert messages[1] == {"role": "assistant", "content": "上一轮助手回复"}
    assert messages[2] == {"role": "user", "content": "本轮任务请求"}


@pytest.mark.asyncio
async def test_runtime_loop_seeds_prior_turns_from_legacy_ctx_extra() -> None:
    session = Session("test-session-legacy")
    set_publish_session(cast("Any", session))

    captured_states: list[AgentState] = []
    bindings = _Bindings(captured_states)
    runtime = CognitiveRuntime(cast("Any", bindings))

    # Test legacy extra fallback
    ctx = RunContext(
        trace_id="trace-legacy",
        session_id="s-legacy",
        extra={
            PRIOR_CONVERSATION_WM_KEY: [
                {"role": "user", "content": "历史问题"},
                {"role": "assistant", "content": "历史答案"},
            ]
        },
    )

    try:
        result = await runtime.run(task="新问题", ctx=ctx)
    finally:
        reset_publish_session(None)

    assert result.status == TaskStatus.COMPLETED
    assert len(captured_states) == 1
    state = captured_states[0]

    # Invariant C4: retired from state.extra
    assert PRIOR_CONVERSATION_WM_KEY not in state.extra

    # Invariant C3: single-track facts preserved
    writer = RunSessionWriter(session=session)
    messages = writer.derive_messages()
    assert len(messages) == 3
    assert messages[0] == {"role": "user", "content": "历史问题"}
    assert messages[1] == {"role": "assistant", "content": "历史答案"}
    assert messages[2] == {"role": "user", "content": "新问题"}


@pytest.mark.asyncio
async def test_runtime_loop_without_prior_turns() -> None:
    session = Session("test-session-empty")
    set_publish_session(cast("Any", session))

    captured_states: list[AgentState] = []
    bindings = _Bindings(captured_states)
    runtime = CognitiveRuntime(cast("Any", bindings))

    ctx = RunContext(trace_id="trace-clean", session_id="s-clean")

    try:
        result = await runtime.run(task="单一请求", ctx=ctx)
    finally:
        reset_publish_session(None)

    assert result.status == TaskStatus.COMPLETED
    assert len(captured_states) == 1
    state = captured_states[0]
    assert PRIOR_CONVERSATION_WM_KEY not in state.extra

    writer = RunSessionWriter(session=session)
    messages = writer.derive_messages()
    assert len(messages) == 1
    assert messages[0] == {"role": "user", "content": "单一请求"}

