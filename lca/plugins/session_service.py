"""Session Service Definition plugin — Tier-1.

Migrated from lca/plugins/session_service/__init__.py. The full SessionService
implementation (with agent_service merge) lives in Task 2.4.5 follow-up work.

For now, this provides a minimal SessionService that records events.
"""

from __future__ import annotations
from typing import Any
from lca.contracts.observability.session_events import SessionEventType
from lca.harness.plugin_api import plugin, PluginKind


class SessionService:
    """Session store + surface projection (model-visible ⟺ logged)."""

    def __init__(self) -> None:
        self._events: list[dict] = []

    async def record(
        self, event_type: SessionEventType, session_id: str, **payload: object
    ) -> None:
        self._events.append({"type": event_type.value, "session_id": session_id, **payload})


@plugin(
    id="lca-session-service",
    provides=["session_service"],
    layer="L0",
    effects="none",
    description="Minimal SessionService — full implementation deferred.",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    kind=PluginKind.SEAM,
)
async def setup(ctx: Any, config: Any) -> None:
    ctx.provide("session_service", SessionService())
