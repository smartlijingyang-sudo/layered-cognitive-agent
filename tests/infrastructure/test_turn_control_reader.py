"""Turn control projection reader tests (ADR-0191 Wave C)."""

from __future__ import annotations

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.policy.budget import create_budget
from lca.contracts.models.core.execution.decision import Decision, Observation, ToolCall, Turn
from lca.contracts.models.core.state.state import AgentState
from lca.infrastructure.session.context.turn_control_reader import (
    append_turn_control_fact,
    consecutive_same_tool,
    control_turns,
    projected_control_turns,
)
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.plugins.loop.reducer.plugin import DefaultReducer
from lca.session.append import Session


def test_commit_turn_appends_turn_control_fact() -> None:
    session = Session("tc_commit")
    token = set_publish_session(session)
    try:
        reducer = DefaultReducer()
        turn = Turn(
            decision=Decision(
                decision_id="d1",
                action_type=ActionType.USE_TOOL,
                rationale="r",
                confidence=1.0,
                tool_calls=[ToolCall(call_id="c1", tool_name="search", arguments={"q": "x"})],
            ),
            observation=Observation(
                observation_id="o1",
                success=False,
                payload=None,
                error="timeout",
            ),
        )
        state = AgentState(trace_id="t", task="task", budget=create_budget(max_steps=8))
        reducer.commit_turn(state, turn)
        projected = projected_control_turns(state)
        assert projected is not None
        assert len(projected) == 1
        assert projected[0].tool_name == "search"
        assert projected[0].observation_success is False
    finally:
        reset_publish_session(token)


def test_gates_prefer_session_projection_over_history() -> None:
    session = Session("tc_gate")
    append_turn_control_fact(
        session,
        Turn(
            decision=Decision(
                decision_id="d1",
                action_type=ActionType.USE_TOOL,
                rationale="r",
                confidence=1.0,
                tool_calls=[ToolCall(call_id="c1", tool_name="search", arguments={})],
            ),
            observation=Observation(observation_id="o1", success=True, payload={"ok": True}),
        ),
    )
    token = set_publish_session(session)
    try:
        state = AgentState(trace_id="t", task="task", budget=create_budget(max_steps=8))
        assert consecutive_same_tool(state, "search") == 1
        assert control_turns(state)[0].tool_name == "search"
    finally:
        reset_publish_session(token)
