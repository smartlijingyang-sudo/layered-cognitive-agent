"""Delivery evidence fold tests."""

from __future__ import annotations

from lca.cognition.convergence.evidence import build_delivery_evidence
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import Decision, Observation, ToolCall, Turn
from lca.contracts.models.core.state.state import AgentState, Budget


def test_listfiles_substantive_stdout_satisfies_unknown_task() -> None:
    file_list = '[{"name": ".lca", "type": "directory"}, {"name": "outputs", "type": "directory"}]'
    state = AgentState(
        trace_id="t",
        task="Use listFiles once on . then reply with file count only.",
        budget=Budget(),
    )
    state.history.append(
        Turn(
            decision=Decision(
                decision_id="d0",
                action_type=ActionType.USE_TOOL,
                rationale="list",
                confidence=0.9,
                tool_calls=[ToolCall(call_id="c0", tool_name="listFiles", arguments={})],
            ),
            observation=Observation(
                observation_id="o0",
                success=True,
                payload={"stdout": file_list},
            ),
        )
    )
    evidence = build_delivery_evidence(state)
    assert evidence.satisfied is True
    assert evidence.has_user_visible_text is True
