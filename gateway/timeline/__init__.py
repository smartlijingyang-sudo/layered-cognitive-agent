"""Agent Timeline (timeline.v1) — sole UI stream for LCA agent runs.

Journal remains full SSOT. UI only sees the closed event set in protocol.py.
"""

from gateway.timeline.projector import TimelineProjector
from gateway.timeline.protocol import EVENT_TYPES, TIMELINE_V, encode_sse, encode_sse_bytes
from gateway.timeline.stream import project_all, stream_timeline_sse

__all__ = [
    "EVENT_TYPES",
    "TIMELINE_V",
    "TimelineProjector",
    "encode_sse",
    "encode_sse_bytes",
    "project_all",
    "stream_timeline_sse",
]
