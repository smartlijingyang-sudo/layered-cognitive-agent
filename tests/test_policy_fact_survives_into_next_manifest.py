"""PR4: PolicyFact emitted by RepeatToolCallGate reaches the next ContextManifest."""

from __future__ import annotations

import pytest

from lca.cognition.brain.decision_gates import RepeatToolCallGate
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Decision, Observation, ToolCall, Turn
from lca.contracts.models.core.state.state import AgentState, Budget
from tests.support.session_gate_helpers import (
    bound_session,
    extend_control_turns,
    gate_decisions_for_step,
)


def _state() -> AgentState:
    budget = Budget(max_steps=10)
    return AgentState(trace_id=new_id("trace"), task="t", budget=budget)


def _tool_decision(tool: str) -> Decision:
    return Decision(
        decision_id=new_id("dec"),
        action_type="use_tool",
        rationale="x",
        confidence=0.5,
        tool_calls=[ToolCall(call_id=new_id("tc"), tool_name=tool, arguments={})],
    )


def _failed_obs(tool: str) -> Observation:
    return Observation(
        observation_id=new_id("obs"),
        success=False,
        payload="",
        error="boom",
        tool_call_id="x",
    )


@pytest.mark.asyncio
async def test_repeat_tool_call_emits_policy_fact() -> None:
    with bound_session():
        state = _state()
        tool = "executeCode"
        for _ in range(3):
            extend_control_turns(
                state,
                [
                    Turn(
                        decision=_tool_decision(tool),
                        observation=_failed_obs(tool),
                    )
                ],
            )
        gate = RepeatToolCallGate()
        decision = _tool_decision(tool)
        out = await gate.enforce(state, decision)
        assert out is decision
        bucket = gate_decisions_for_step(state)
        assert len(bucket) == 1
        event = bucket[0]
        assert event.gate == "RepeatToolCallGate"
        assert event.verdict == "warn"
        assert event.is_rewritten is False
        assert event.policy_fact is not None
        assert event.policy_fact.kind == "repeat_tool_call"
        assert tool in event.policy_fact.message


@pytest.mark.asyncio
async def test_warnings_accumulate_so_next_manifest_can_fold() -> None:
    with bound_session():
        state = _state()
        gate = RepeatToolCallGate()
        extend_control_turns(
            state,
            (
                Turn(
                    decision=_tool_decision("executeCode"),
                    observation=_failed_obs("executeCode"),
                )
                for _ in range(3)
            ),
        )
        await gate.enforce(state, _tool_decision("executeCode"))
        bucket = gate_decisions_for_step(state)
        assert len(bucket) == 1
        pf = bucket[0].policy_fact
        assert pf is not None
        assert pf.source == "repeat_tool_call"
