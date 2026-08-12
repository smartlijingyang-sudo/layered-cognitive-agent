"""SSE 编码 — 无状态工具函数。

dict → SSE 帧 bytes。纯函数，无状态。
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
        "reconnect.gap",
    }
)


def encode_sse(event: dict[str, Any], *, seq: int, event_type: str) -> bytes:
    """dict → SSE 帧 bytes。纯函数，无状态。

    event_type 必须在 EVENT_TYPES 中，否则 ValueError。
    """
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown timeline event type: {event_type!r}")
    payload = {"v": TIMELINE_V, **event}
    data = json.dumps(payload, ensure_ascii=False, default=str)
    return f"id: {seq}\nevent: {event_type}\ndata: {data}\n\n".encode()


def encode_sse_legacy(event: dict[str, Any], *, seq: int) -> bytes:
    """兼容旧接口的编码（不传 event_type，从 event['type'] 取）。

    仅供过渡期使用，新代码应使用 encode_sse()。
    """
    etype = str(event.get("type", ""))
    if etype not in EVENT_TYPES:
        raise ValueError(f"unknown timeline event type: {etype!r}")
    return encode_sse(event, seq=seq, event_type=etype)
