"""Stop policy delivery-satisfied backup (ADR-0196 CV4)."""

from __future__ import annotations

from lca.contracts.atoms.enums.enums import ActionType, ReflectionVerdict
from lca.contracts.models.core.execution.decision import (
    Decision,
    Observation,
    Reflection,
    ToolCall,
    Turn,
)
from lca.contracts.models.core.policy.budget import create_budget
from lca.contracts.models.core.state.state import AgentState
from lca.plugins.loop.state.stop_policy.plugin import DefaultStopPolicy


class _StubClosure:
    def synthesize(self) -> str | None:
        return None


def test_delivery_satisfied_stops_after_producer_success_without_respond() -> None:
    state = AgentState(
        trace_id="t",
        task="这个是什么",
        budget=create_budget(max_steps=8),
    )
    state.control_turns.append(
        Turn(
            decision=Decision(
                decision_id="d0",
                action_type=ActionType.USE_TOOL,
                rationale="read",
                confidence=0.9,
                tool_calls=[ToolCall(call_id="c0", tool_name="executeCode", arguments={})],
            ),
            observation=Observation(
                observation_id="o0",
                success=True,
                payload={"stdout": "算力资源使用报告模板\n" + ("章节\n" * 20)},
            ),
        )
    )
    decision = Decision(
        decision_id="d1",
        action_type=ActionType.USE_TOOL,
        rationale="again",
        confidence=0.9,
        tool_calls=[ToolCall(call_id="c1", tool_name="activate_skill", arguments={})],
    )
    reflection = Reflection(
        reflection_id="r1",
        verdict=ReflectionVerdict.ON_TRACK,
        lesson="ok",
    )
    stop = DefaultStopPolicy(_StubClosure()).decide(state, decision, None, reflection)
    assert stop.should_stop is True
    assert stop.final_output
    assert "算力" in stop.final_output or "交付" in stop.final_output or "工作区" in stop.final_output
