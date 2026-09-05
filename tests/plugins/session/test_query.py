"""Wave 5: session 事件查询 + tool 对齐 fold。"""

from __future__ import annotations

from lca.plugins.session.runtime.query import filter_session_events, fold_tool_invocations
from lca_kernel.events.session import SessionEvent


def _event(
    seq: int,
    event_type: str,
    data: dict | None = None,
    *,
    time: int | None = None,
) -> SessionEvent:
    return SessionEvent(
        type=event_type,
        seq=seq,
        time=time if time is not None else seq * 1000,
        data=data or {},
        session_id="run_q",
    )


def test_filter_by_type_turn_step() -> None:
    events = (
        _event(0, "turn.started.v1", {"turn": 1}),
        _event(1, "step.started.v1", {"turn": 1, "step": 1}),
        _event(2, "message.accepted.v1", {"message_id": "m1"}),
        _event(3, "step.ended.v1", {"turn": 1, "step": 1}),
        _event(4, "turn.ended.v1", {"turn": 1, "reason": "done"}),
        _event(5, "turn.started.v1", {"turn": 2}),
        _event(6, "step.started.v1", {"turn": 2, "step": 1}),
        _event(7, "assistant.responded.v1", {"turn": 2, "step": 1, "content": "x"}),
    )
    turn1 = filter_session_events(events, turn=1)
    assert [e.seq for e in turn1] == [0, 1, 2, 3, 4]
    step1_turn2 = filter_session_events(events, turn=2, step=1)
    assert [e.seq for e in step1_turn2] == [6, 7]
    accepted = filter_session_events(events, event_type="message.accepted.v1")
    assert len(accepted) == 1
    assert accepted[0].seq == 2


def test_fold_tool_invocations_pairs_start_end() -> None:
    events = (
        _event(0, "turn.started.v1", {"turn": 1}),
        _event(1, "step.started.v1", {"turn": 1, "step": 2}),
        _event(
            2,
            "body.tool.execute.start",
            {"invocation_id": "inv_a", "tool_name": "bash", "turn": 1, "step": 2},
            time=1000,
        ),
        _event(
            3,
            "body.tool.execute.end",
            {"invocation_id": "inv_a", "outcome": "success", "turn": 1, "step": 2},
            time=1500,
        ),
    )
    views = fold_tool_invocations(events)
    assert len(views) == 1
    view = views[0]
    assert view.invocation_id == "inv_a"
    assert view.tool_name == "bash"
    assert view.turn == 1
    assert view.step == 2
    assert view.started_seq == 2
    assert view.ended_seq == 3
    assert view.ok is True
    assert view.duration_ms == 500


def test_fold_tool_invocations_open_start_without_end() -> None:
    events = (
        _event(
            0,
            "spine.body.tool.execute.start",
            {"invocation_id": "inv_open", "tool_name": "read"},
        ),
    )
    views = fold_tool_invocations(events)
    assert len(views) == 1
    assert views[0].ended_seq is None
    assert views[0].ok is None
