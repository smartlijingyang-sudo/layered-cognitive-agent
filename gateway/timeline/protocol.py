"""Agent Timeline wire contract (timeline.v1).

Closed event set for UI consumption. Journal remains full SSOT on disk;
only events listed here leave the gateway toward LobeHub.
"""

from __future__ import annotations

import json
from typing import Any, Final

TIMELINE_V: Final = "timeline.v1"

# Closed set — anything else is a bug if emitted.
EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "run.start",
        "thinking.delta",
        "thinking.end",
        "answer.delta",
        "tool.start",
        "tool.delta",
        "tool.end",
        "run.end",
    }
)


def encode_sse(event: dict[str, Any], *, seq: int) -> str:
    """Encode one timeline event as a standard SSE frame."""
    etype = str(event.get("type", ""))
    if etype not in EVENT_TYPES:
        raise ValueError(f"unknown timeline event type: {etype!r}")
    payload = {"v": TIMELINE_V, **event}
    data = json.dumps(payload, ensure_ascii=False, default=str)
    return f"id: {seq}\nevent: {etype}\ndata: {data}\n\n"


def encode_sse_bytes(event: dict[str, Any], *, seq: int) -> bytes:
    return encode_sse(event, seq=seq).encode("utf-8")
