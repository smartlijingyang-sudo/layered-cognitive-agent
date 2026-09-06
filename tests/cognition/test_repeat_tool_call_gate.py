"""RepeatToolCallGate identical-args tests (ADR-0197)."""

from __future__ import annotations

import asyncio

from lca.cognition.brain.decision_gates.repeat.tool_call import RepeatToolCallGate
from lca.cognition.brain.guard.loop_policy import LoopGuardPolicyView, StaticLoopGuardPolicy
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import Decision, Observation, ToolCall, Turn
from lca.contracts.models.core.policy.loop_policy import LoopPolicyThresholds
from lca.contracts.models.core.state.state import AgentState, Budget
from tests.support.session_gate_helpers import bound_session, extend_control_turns, gate_decisions_for_step


def _tool_turn(tool_name: str, arguments: dict[str, object]) -> Turn:
    return Turn(
        decision=Decision(
            decision_id="d-prev",
            action_type=ActionType.USE_TOOL,
            rationale="r",
            confidence=1.0,
            tool_calls=[ToolCall(call_id="c1", tool_name=tool_name, arguments=arguments)],
        ),
        observation=Observation(observation_id="o1", success=True, payload={"ok": True}),
    )


def test_repeat_gate_ignores_same_tool_different_args() -> None:
    policy = StaticLoopGuardPolicy(
        LoopGuardPolicyView(
            thresholds=LoopPolicyThresholds(repeat_warn=2),
            repeat_thresholds=(3, 5),
        )
    )
    gate = RepeatToolCallGate(policy=policy)
    with bound_session("repeat_diff_args") as _session:
        state = AgentState(trace_id="t", task="demo", budget=Budget())
        extend_control_turns(
            state,
            (
                _tool_turn("read", {"path": "a"}),
                _tool_turn("read", {"path": "b"}),
            ),
        )
        decision = Decision(
            decision_id="d1",
            action_type=ActionType.USE_TOOL,
            rationale="r",
            confidence=1.0,
            tool_calls=(ToolCall(call_id="c2", tool_name="read", arguments={"path": "b"}),),
        )
        result = asyncio.run(gate.enforce(state, decision))
        assert result.action_type == ActionType.USE_TOOL
        assert not gate_decisions_for_step(state)


def test_repeat_gate_warns_on_identical_args() -> None:
    policy = StaticLoopGuardPolicy(
        LoopGuardPolicyView(
            thresholds=LoopPolicyThresholds(repeat_warn=2),
            repeat_thresholds=(2, 4),
        )
    )
    gate = RepeatToolCallGate(policy=policy)
    args = {"path": "same"}
    with bound_session("repeat_identical") as _session:
        state = AgentState(trace_id="t", task="demo", budget=Budget())
        extend_control_turns(
            state,
            (
                _tool_turn("read", dict(args)),
                _tool_turn("read", dict(args)),
            ),
        )
        decision = Decision(
            decision_id="d1",
            action_type=ActionType.USE_TOOL,
            rationale="r",
            confidence=1.0,
            tool_calls=(ToolCall(call_id="c2", tool_name="read", arguments=dict(args)),),
        )
        result = asyncio.run(gate.enforce(state, decision))
        assert result.action_type == ActionType.USE_TOOL
        assert gate_decisions_for_step(state)
