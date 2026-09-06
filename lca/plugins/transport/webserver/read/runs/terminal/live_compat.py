"""Gateway live-tail compatibility facade.

Runtime journal projection belongs to L0 observability. This module preserves
the historical Gateway import path for HTTP handlers and external callers while
keeping live-tail behavior in the infrastructure implementation.
"""

from lca.infrastructure.observability.journal.stream.live_tail import (
    TEXT_CHANNEL_ALL,
    TEXT_CHANNEL_ANSWER,
    LiveGap,
    LiveTail,
    encode_live_gap,
    iter_live_sse,
)

__all__ = [
    "TEXT_CHANNEL_ALL",
    "TEXT_CHANNEL_ANSWER",
    "LiveGap",
    "LiveTail",
    "encode_live_gap",
    "iter_live_sse",
]
