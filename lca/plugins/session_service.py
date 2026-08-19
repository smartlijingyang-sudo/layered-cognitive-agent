"""Session Service Definition plugin — Tier-1.

Migrated from lca/plugins/session_service/__init__.py. The full SessionService
implementation (with agent_service merge) lives in Task 2.4.5 follow-up work.

For now, this provides a minimal SessionService that records events.
"""
from __future__ import annotations

from cordis import plugin

from lca.contracts.observability.session_events import SessionEventType


class SessionService:
    """Session store + surface projection (model-visible ⟺ logged)."""

    def __init__(self) -> None:
        self._events: list[dict] = []

    async def record(
        self,
        event_type: SessionEventType,
        session_id: str,
        **payload: object,
    ) -> None:
        self._events.append(
            {"type": event_type.value, "session_id": session_id, **payload}
        )


@plugin(name="lca-session-service")
async def setup(ctx, config) -> None:
    ctx.provide("session_service", SessionService())
