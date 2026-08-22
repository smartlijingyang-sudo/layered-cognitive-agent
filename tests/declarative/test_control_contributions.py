"""Tests for control contribution executors."""

from __future__ import annotations

import pytest

from lca.contracts.atoms.enums import ActionType
from lca.contracts.models.core.budget import Budget
from lca.contracts.models.core.decision import Decision, ToolCall
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.declarative_phase_graph import PhaseInput
from lca.layer2_runtime.control_runtime import ControlVerdictKind
from lca.plugins.control_contributions import (
    ActAuthorizeExecutor,
    ActBudgetExecutor,
    ActConstrainExecutor,
    ActExecuteExecutor,
    ActSafeBoundaryExecutor,
    ObserveCheckpointExecutor,
    PerceiveContextExecutor,
    RememberAdmitExecutor,
    StopDecideExecutor,
    ThinkGuardExecutor,
)


class MockContext:
    """Mock context for testing."""

    def __init__(self, state, decision=None, observation=None, reflection=None, checkpoint_reason=None):
        self.state = state
        self.decision = decision
        self.observation = observation
        self.reflection = reflection
        self.checkpoint_reason = checkpoint_reason


def _make_working_state() -> AgentState:
    """Create a working state."""
    return AgentState(
        trace_id="test-trace",
        task="test task",
        step=0,
        budget=Budget(max_steps=10),
    )


@pytest.mark.asyncio
async def test_perceive_context_allows_working_state():
    """Test perceive-context allows working state."""
    executor = PerceiveContextExecutor()
    state = _make_working_state()
    context = MockContext(state)
    result = await executor.execute(context, PhaseInput())
    assert result.payload.kind == ControlVerdictKind.ALLOW


@pytest.mark.asyncio
async def test_act_budget_allows_within_budget():
    """Test act-budget allows when within budget."""
    executor = ActBudgetExecutor()
    state = _make_working_state()
    context = MockContext(state)
    result = await executor.execute(context, PhaseInput())
    assert result.payload.kind == ControlVerdictKind.ALLOW


@pytest.mark.asyncio
async def test_act_budget_exhausted():
    """Test act-budget returns exhausted when over budget."""
    executor = ActBudgetExecutor()
    state = _make_working_state()
    state.budget = Budget(max_steps=0)
    state.budget.used_steps = 1
    context = MockContext(state)
    result = await executor.execute(context, PhaseInput())
    assert result.payload.kind == ControlVerdictKind.EXHAUSTED


@pytest.mark.asyncio
async def test_act_authorize_allows_valid_tool_action():
    """Test act-authorize allows valid tool action."""
    executor = ActAuthorizeExecutor()
    state = _make_working_state()
    decision = Decision(
        decision_id="d1",
        action_type=ActionType.USE_TOOL,
        rationale="test",
        confidence=1.0,
        tool_calls=[ToolCall(call_id="c1", tool_name="bash", arguments={})],
    )
    context = MockContext(state, decision=decision)
    result = await executor.execute(context, PhaseInput())
    assert result.payload.kind == ControlVerdictKind.ALLOW


@pytest.mark.asyncio
async def test_act_authorize_denies_unnamed_tool():
    """Test act-authorize denies unnamed tool."""
    executor = ActAuthorizeExecutor()
    state = _make_working_state()
    decision = Decision(
        decision_id="d1",
        action_type=ActionType.USE_TOOL,
        rationale="test",
        confidence=1.0,
        tool_calls=[ToolCall(call_id="c1", tool_name="", arguments={})],
    )
    context = MockContext(state, decision=decision)
    result = await executor.execute(context, PhaseInput())
    assert result.payload.kind == ControlVerdictKind.DENY


@pytest.mark.asyncio
async def test_act_constrain_allows_valid_call_ids():
    """Test act-constrain allows valid call IDs."""
    executor = ActConstrainExecutor()
    state = _make_working_state()
    decision = Decision(
        decision_id="d1",
        action_type=ActionType.USE_TOOL,
        rationale="test",
        confidence=1.0,
        tool_calls=[
            ToolCall(call_id="c1", tool_name="bash", arguments={}),
            ToolCall(call_id="c2", tool_name="ls", arguments={}),
        ],
    )
    context = MockContext(state, decision=decision)
    result = await executor.execute(context, PhaseInput())
    assert result.payload.kind == ControlVerdictKind.ALLOW


@pytest.mark.asyncio
async def test_act_constrain_denies_duplicate_call_ids():
    """Test act-constrain denies duplicate call IDs."""
    executor = ActConstrainExecutor()
    state = _make_working_state()
    decision = Decision(
        decision_id="d1",
        action_type=ActionType.USE_TOOL,
        rationale="test",
        confidence=1.0,
        tool_calls=[
            ToolCall(call_id="c1", tool_name="bash", arguments={}),
            ToolCall(call_id="c1", tool_name="ls", arguments={}),
        ],
    )
    context = MockContext(state, decision=decision)
    result = await executor.execute(context, PhaseInput())
    assert result.payload.kind == ControlVerdictKind.DENY


@pytest.mark.asyncio
async def test_stop_decide_allows_continuation():
    """Test stop-decide allows continuation when not exhausted."""
    executor = StopDecideExecutor()
    state = _make_working_state()
    context = MockContext(state)
    result = await executor.execute(context, PhaseInput())
    assert result.payload.kind == ControlVerdictKind.ALLOW


@pytest.mark.asyncio
async def test_stop_decide_stops_on_exhaustion():
    """Test stop-decide stops when budget exhausted."""
    executor = StopDecideExecutor()
    state = _make_working_state()
    state.budget = Budget(max_steps=0)
    state.budget.used_steps = 1
    context = MockContext(state)
    result = await executor.execute(context, PhaseInput())
    assert result.payload.kind == ControlVerdictKind.STOP


@pytest.mark.asyncio
async def test_observe_checkpoint_allows_valid_step():
    """Test observe-checkpoint allows valid step."""
    executor = ObserveCheckpointExecutor()
    state = _make_working_state()
    context = MockContext(state)
    result = await executor.execute(context, PhaseInput())
    assert result.payload.kind == ControlVerdictKind.ALLOW
