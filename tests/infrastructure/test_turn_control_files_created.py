"""Turn control files_created fold tests (ADR-0196)."""

from __future__ import annotations

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import Decision, Observation, ToolCall, Turn
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.infrastructure.session.context.turn_control_reader import (
    append_turn_control_fact,
    control_turns,
)
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.plugins.session.session_turn_control.session_turn_control import TurnControlUnit
from lca.session.append import Session
from lca_kernel.events.session.session import SessionEvent


def _event(seq: int, event_type: str, data: dict) -> SessionEvent:
    return SessionEvent(
        session_id="s1",
        seq=seq,
        type=event_type,
        time=float(seq),
        data=data,
        actor="test",
        visibility="internal",
    )


def test_turn_control_folds_files_created() -> None:
    unit = TurnControlUnit()
    state = unit.init(None)
    state = unit.apply(
        state,
        _event(
            0,
            "turn.control.v1",
            {
                "action_type": "use_tool",
                "tool_name": "executeCode",
                "observation_success": True,
                "files_created": ("graphplan_joke.py",),
            },
        ),
    )
    view = unit.view(state)
    assert view["turns"][0]["files_created"] == ("graphplan_joke.py",)


def test_append_turn_control_fact_extracts_files_from_observation_extra() -> None:
    session = Session("fc_1")
    append_turn_control_fact(
        session,
        Turn(
            decision=Decision(
                decision_id="d1",
                action_type=ActionType.USE_TOOL,
                rationale="r",
                confidence=1.0,
                tool_calls=[ToolCall(call_id="c1", tool_name="executeCode", arguments={})],
            ),
            observation=Observation(
                observation_id="o1",
                success=True,
                payload={"stdout": "ok" * 30},
                extra={"files_created": ["out.py"]},
            ),
        ),
    )
    agent_state = AgentState(trace_id="t", task="t", budget=Budget())
    token = set_publish_session(session)
    try:
        turns = control_turns(agent_state)
        assert turns[0].files_created == ("out.py",)
    finally:
        reset_publish_session(token)
