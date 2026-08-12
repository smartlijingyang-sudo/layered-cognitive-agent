"""Stream helpers for timeline.v1 SSE."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from gateway.timeline.projector import TimelineProjector
from gateway.timeline.protocol import encode_sse_bytes
from lca.contracts.models.observability.journal import StampedEvent


async def stream_timeline_sse(
    event_stream: AsyncIterator[StampedEvent],
    *,
    after_seq: int = 0,
    projector: TimelineProjector | None = None,
) -> AsyncIterator[bytes]:
    """Yield timeline.v1 SSE frames from a typed journal stream."""
    proj = projector or TimelineProjector()
    async for stamped in event_stream:
        if stamped.seq <= after_seq:
            continue
        for ev in proj.project(stamped):
            yield encode_sse_bytes(ev, seq=int(ev.get("seq") or stamped.seq))


def project_all(stamped_events: list[StampedEvent]) -> list[dict[str, Any]]:
    """Synchronous project for tests / fixtures."""
    proj = TimelineProjector()
    out: list[dict[str, Any]] = []
    for s in stamped_events:
        out.extend(proj.project(s))
    return out
