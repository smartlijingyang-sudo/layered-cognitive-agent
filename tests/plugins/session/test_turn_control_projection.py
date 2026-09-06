"""TurnControlUnit projection fold tests."""

from __future__ import annotations

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


def test_turn_control_folds_turn_end_and_reducer_marker() -> None:
    unit = TurnControlUnit()
    state = unit.init(None)
    state = unit.apply(state, _event(0, "turn.ended.v1", {"turn": 1, "reason": "completed"}))
    state = unit.apply(
        state,
        _event(
            1,
            "spine.runtime.reducer.apply",
            {"method": "apply_turn", "action_type": "use_tool", "tool_name": "search"},
        ),
    )
    view = unit.view(state)
    assert view["turns"] == [{"turn": 1, "reason": "completed"}]
    assert view["last_action_type"] == "use_tool"
    assert view["last_tool_name"] == "search"


def test_turn_control_registry_via_session_projection() -> None:
    unit = TurnControlUnit()
    session = Session("tc_1")
    session.append("turn.ended.v1", {"turn": 2, "reason": "completed"})
    state = unit.init(session.header)
    for event in session.snapshot_events():
        state = unit.apply(state, event)
    assert unit.view(state)["turns"] == [{"turn": 2, "reason": "completed"}]
