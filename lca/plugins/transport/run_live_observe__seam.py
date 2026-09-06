"""Run live observe seam — journal tail → four UI SSE events (ADR-0100, C7).

Single entry for the observation face: subscribe to ``LiveRunProjection``,
encode via :class:`RunUiEncoder`, resolve terminal hints from journal fold
with carrier fallback. HTTP handlers stay thin; tests target this seam.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

import structlog

from lca.contracts.observability.run_live import LiveTerminalHint
from lca.plugins.transport.run_ui_encoder__encoder_provider import RunUiEncoder
from lca.plugins.transport.webserver.handlers.runs.session.session.session import RunSession
from lca.plugins.transport.webserver.handlers.runs.terminal.status.status import (
    resolve_live_terminal_hint_dto,
)

_log = structlog.get_logger(__name__)


class RunLiveObserveSeam:
    """Observation-face coordinator: tail subscription + UI encoding + terminal hint."""

    def __init__(self, *, encoder: RunUiEncoder | None = None) -> None:
        self._encoder = encoder or RunUiEncoder()

    @staticmethod
    def terminal_hint(session: RunSession) -> LiveTerminalHint:
        return resolve_live_terminal_hint_dto(session)

    async def stream(
        self,
        session: RunSession,
        *,
        after: int = 0,
    ) -> AsyncIterator[bytes]:
        """Yield ADR-0100 SSE frames for one run live subscription."""
        first_frame = True
        try:
            async for line in self._encoder.encode_live_tail(
                session.tail,
                after_seq=after,
                terminal_hint=lambda: self.terminal_hint(session).as_tuple(),
            ):
                if first_frame:
                    first_frame = False
                    started_at = getattr(session, "started_at", None)
                    if isinstance(started_at, (int, float)) and started_at > 0:
                        _log.info(
                            "run_live_first_frame",
                            run_id=session.run_id,
                            latency_ms=int((time.time() - started_at) * 1000),
                        )
                yield line
        except asyncio.CancelledError:
            return


_default_seam = RunLiveObserveSeam()


def stream_run_live_observe(
    session: RunSession,
    *,
    after: int = 0,
) -> AsyncIterator[bytes]:
    """Module-level entry used by transport read paths."""
    return _default_seam.stream(session, after=after)


__all__ = [
    "RunLiveObserveSeam",
    "stream_run_live_observe",
]
