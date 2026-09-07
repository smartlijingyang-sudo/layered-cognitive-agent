"""TurnControlUnit projection fold tests."""

from __future__ import annotations

from lca.contracts.protocols.session.control_state import TurnControlProjection
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


def test_turn_control_satisfies_projection_protocol() -> None:
    """TurnControlUnit must satisfy the gate-facing TurnControlProjection Protocol."""
    assert isinstance(TurnControlUnit(), TurnControlProjection)


def test_fold_returns_control_state_without_session() -> None:
    """fold() on a Session-less target returns an empty ControlState, not None.

    Gates must treat empty projection as 'no control signal' — the
    legacy ``state.control_turns`` history fallback was removed in
    Wave C1 (ADR-0191 §C1).
    """
    unit = TurnControlUnit()

    class _NoSession:
        pass

    snapshot = unit.fold(_NoSession())
    assert snapshot.turns == ()
    assert snapshot.last_action_type is None
    assert snapshot.last_tool_name is None


def test_fold_excludes_turn_end_markers_from_gate_view() -> None:
    """``turn.ended.v1`` markers advance the cursor but are not gate entries."""
    unit = TurnControlUnit()
    session = Session("tc_fold")
    session.append("turn.control.v1", {"action_type": "use_tool", "tool_name": "search"})
    session.append("turn.ended.v1", {"turn": 1, "reason": "completed"})
    snapshot = unit.fold(session)
    assert len(snapshot.turns) == 1
    assert snapshot.turns[0].action_type == "use_tool"
    assert snapshot.turns[0].tool_name == "search"
    # last_action_type is updated by the cursor, not from turn.ended markers
    assert snapshot.last_action_type == "use_tool"
    assert snapshot.last_tool_name == "search"
