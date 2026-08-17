"""Bridge old /runs/* API to new /v1/sessions/* command API (spec §B.7).

LegacyApiAdapter translates synchronous /runs/* requests into the async
command flow: create session → send message → wait for terminal state →
return projection snapshot in the legacy TaskResult shape.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

_log = structlog.get_logger(__name__)


class LegacyApiAdapter:
    """Translates synchronous /runs/* requests to async command flow.

    POST /runs             → create session + send message + wait for result
    GET  /runs/{id}        → projection snapshot → TaskResult format
    GET  /runs/{id}/live   → ProjectionChange SSE → LiveTail SSE format
    POST /runs/{id}/answer → AnswerCommand
    """

    #: Projection statuses that terminate the wait loop.
    _TERMINAL_STATUSES: frozenset[str] = frozenset(
        {"completed", "failed", "canceled", "waiting_input"}
    )

    def __init__(self, gateway: Any) -> None:
        self._gateway = gateway

    async def _wait_for_terminal_state(
        self,
        session_id: str,
        *,
        timeout_s: float = 120.0,
        poll_interval_s: float = 0.2,
    ) -> Any:
        """Wait until session reaches a terminal state or timeout.

        Terminal states: completed, failed, canceled, waiting_input.
        On timeout, returns the current projection snapshot.
        Uses ``time.monotonic()`` for wall-clock measurement and
        ``asyncio.sleep()`` between polls.
        """
        deadline = time.monotonic() + timeout_s

        while time.monotonic() < deadline:
            snapshot = await self._gateway.get_snapshot(session_id)
            status = snapshot.values.get("activity", {}).get("status")
            if status in self._TERMINAL_STATUSES:
                return snapshot
            await asyncio.sleep(poll_interval_s)

        # Timeout — return current state
        _log.warning(
            "legacy_adapter.timeout",
            session_id=session_id,
            timeout_s=timeout_s,
        )
        return await self._gateway.get_snapshot(session_id)
