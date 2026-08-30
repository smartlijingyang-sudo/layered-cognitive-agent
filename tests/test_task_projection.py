from __future__ import annotations

from lca.contracts.harness.tasks.session import SessionEvent
from lca.harness.projection.web import TaskProjection


def _event(seq: int, event_type: str, data: dict[str, object]) -> SessionEvent:
    return SessionEvent(type=event_type, seq=seq, time=seq, data=data, session_id="s-1")


def test_task_projection_replays_lifecycle() -> None:
    projection = TaskProjection()
    state = projection.init()

    state = projection.apply(
        state,
        _event(
            0,
            "TaskCreated",
            {"task_id": "t-1", "objective": "analyze", "profile": "standard"},
        ),
    )
    state = projection.apply(state, _event(1, "task.started.v1", {}))
    state = projection.apply(state, _event(2, "task.completed.v1", {"status": "succeeded"}))

    assert projection.view(state) == {
        "task_id": "t-1",
        "session_id": "s-1",
        "objective": "analyze",
        "profile": "standard",
        "status": "succeeded",
        "last_seq": 2,
    }


def test_task_projection_ignores_out_of_order_events_after_terminal_state() -> None:
    projection = TaskProjection()
    state = projection.init()
    state = projection.apply(
        state,
        _event(2, "task.completed.v1", {"status": "succeeded"}),
    )

    state = projection.apply(state, _event(1, "task.started.v1", {}))
    state = projection.apply(state, _event(2, "task.failed.v1", {}))

    assert state["status"] == "succeeded"
    assert state["last_seq"] == 2
