"""Structural domain events → Session spine, with structured log when unbound.

Run-bound facts route through ``FactGateway`` (``publish_spine_ep`` /
``publish_ep_bound``; ADR-0194 P2-15). Unbound session → structured
``structlog`` INFO (never silent).
"""

from __future__ import annotations

from typing import Any

import structlog

from lca.infrastructure.session._overflow_0.bindings import resolve_session_reader
from lca.loop.emit.spine.ep import SpineEmitRef, publish_spine_ep

log = structlog.get_logger(__name__)


def publish_structural_event(
    *,
    execution_point: str,
    channel: str,
    payload: dict[str, Any],
    producer: type,
    actor: str = "spine",
) -> SpineEmitRef | None:
    """Publish one structural spine EP via FactGateway (ADR-0194 P2-15)."""
    del producer
    writer = resolve_session_reader()
    if writer is None:
        log.info(
            "domain_event.no_session",
            execution_point=execution_point,
            channel=channel,
            payload=payload,
        )
        return None
    return publish_spine_ep(
        execution_point,
        payload,
        channel=channel,
        actor=actor,
        session=writer,
    )


__all__ = ["publish_structural_event"]
