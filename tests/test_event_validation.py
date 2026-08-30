from __future__ import annotations

import pytest

from lca.contracts.harness.tasks.session import SessionEvent
from lca.harness.session.event_validation import validate_event_stream


def _event(seq: int, session_id: str = "s-1") -> SessionEvent:
    return SessionEvent(type="fact.v1", seq=seq, time=seq, data={}, session_id=session_id)


def test_event_stream_accepts_strictly_increasing_events() -> None:
    validate_event_stream([_event(0), _event(1), _event(2)], session_id="s-1")


@pytest.mark.parametrize("events", [[_event(0), _event(0)], [_event(1), _event(0)], [_event(-1)]])
def test_event_stream_rejects_non_replayable_order(events: list[SessionEvent]) -> None:
    with pytest.raises(ValueError):
        validate_event_stream(events, session_id="s-1")


def test_event_stream_rejects_cross_session_event() -> None:
    with pytest.raises(ValueError, match="another session"):
        validate_event_stream([_event(0), _event(1, "s-2")], session_id="s-1")
