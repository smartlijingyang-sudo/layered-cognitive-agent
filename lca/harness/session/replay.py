"""Deterministic replay helpers for session projections."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from lca.contracts.harness.session import SessionEvent
from lca.harness.session.event_validation import validate_event_stream


class ReplayProjection(Protocol):
    def init(self) -> dict[str, Any]: ...
    def apply(self, state: dict[str, Any], event: SessionEvent) -> dict[str, Any]: ...


def replay_projection(
    projection: ReplayProjection,
    events: Sequence[SessionEvent],
    *,
    session_id: str,
) -> dict[str, Any]:
    """Validate and fold a complete event sequence into a fresh projection state."""

    validate_event_stream(events, session_id=session_id)
    state = projection.init()
    for event in events:
        state = projection.apply(state, event)
    return state


__all__ = ["ReplayProjection", "replay_projection"]
