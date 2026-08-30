"""Flush buffered observability exporters after a legacy run is terminalized."""

from __future__ import annotations

import asyncio

import structlog

from lca.infrastructure.observability import BoundObservability

EXPORT_DISPOSE_TIMEOUT_S = 3.0
_log = structlog.get_logger(__name__)


async def dispose_export(hub: BoundObservability) -> None:
    """Flush Langfuse or OTel exporters outside the event loop with bounded waiting."""
    try:
        await asyncio.wait_for(
            asyncio.to_thread(hub.flush),
            timeout=EXPORT_DISPOSE_TIMEOUT_S,
        )
    except TimeoutError:
        _log.warning("observability_export_flush_timeout", hop="H3")
    except Exception:
        _log.warning("observability_export_flush_failed", hop="H3", exc_info=True)


__all__ = ["EXPORT_DISPOSE_TIMEOUT_S", "dispose_export"]
