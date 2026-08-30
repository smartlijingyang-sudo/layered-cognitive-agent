"""Deterministic validation for replayable session event streams."""

from __future__ import annotations

from collections.abc import Iterable

from lca.contracts.harness.tasks.session import SessionEvent


def validate_event_stream(events: Iterable[SessionEvent], *, session_id: str) -> None:
    """Reject event streams that cannot be safely replayed."""

    previous = -1
    for event in events:
        if event.session_id != session_id:
            raise ValueError("event belongs to another session")
        if event.seq <= previous:
            raise ValueError("session event sequence must increase strictly")
        if event.seq < 0:
            raise ValueError("session event sequence must be non-negative")
        previous = event.seq


__all__ = ["validate_event_stream"]
