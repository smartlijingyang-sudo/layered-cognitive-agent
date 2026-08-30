from __future__ import annotations

import pytest

from lca.contracts.harness.session import SessionEvent
from lca.harness.projection.web import TaskProjection
from lca.harness.session.replay import replay_projection


def _event(seq: int, event_type: str, data: dict[str, object]) -> SessionEvent:
    return SessionEvent(event_type, seq, seq, data, "s-1")


def test_replay_projection_rebuilds_task_state() -> None:
    state = replay_projection(
        TaskProjection(),
        [
            _event(0, "task.created.v1", {"task_id": "t-1", "objective": "demo"}),
            _event(1, "task.started.v1", {}),
        ],
        session_id="s-1",
    )
    assert state["task_id"] == "t-1"
    assert state["status"] == "working"


def test_replay_projection_rejects_out_of_order_events() -> None:
    with pytest.raises(ValueError):
        replay_projection(
            TaskProjection(),
            [_event(1, "task.started.v1", {}), _event(0, "task.created.v1", {})],
            session_id="s-1",
        )
