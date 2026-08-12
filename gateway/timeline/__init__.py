"""Agent Timeline (timeline.v1) — sole UI stream for LCA agent runs.

Journal remains full SSOT. UI only sees the closed event set in sse_encode.py.

Architecture (ADR-0053):
  - TimelineProjection: pure domain mapping (StampedEvent → TimelineEvent)
  - LobeHubSSEAdapter: protocol translation (TimelineEvent → LobeHub wire format)
  - encode_sse: stateless SSE encoding (dict → bytes)
  - compose_sse_stream: unified SSE stream assembly
"""

from gateway.timeline.lobehub_adapter import LobeHubSSEAdapter
from gateway.timeline.projection import TimelineProjection
from gateway.timeline.protocol import EVENT_TYPES, TIMELINE_V
from gateway.timeline.sse_encode import encode_sse, encode_sse_legacy
from gateway.timeline.stream import compose_sse_stream, project_all
from gateway.timeline.types import (
    AnswerDeltaEvent,
    RunEndEvent,
    RunStartEvent,
    ThinkingDeltaEvent,
    ThinkingEndEvent,
    TimelineEvent,
    ToolDeltaEvent,
    ToolEndEvent,
    ToolStartEvent,
)

# Backward-compatible alias for existing imports
TimelineProjector = TimelineProjection

__all__ = [
    "EVENT_TYPES",
    "TIMELINE_V",
    "AnswerDeltaEvent",
    "LobeHubSSEAdapter",
    "RunEndEvent",
    "RunStartEvent",
    "ThinkingDeltaEvent",
    "ThinkingEndEvent",
    "TimelineEvent",
    "TimelineProjection",
    "TimelineProjector",
    "ToolDeltaEvent",
    "ToolEndEvent",
    "ToolStartEvent",
    "compose_sse_stream",
    "encode_sse",
    "encode_sse_legacy",
    "project_all",
]
