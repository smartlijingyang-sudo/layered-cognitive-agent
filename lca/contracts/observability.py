"""第5.9节：可观测性与事件契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from lca.contracts.enums import SpanStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TraceSpan:
    span_id: str
    trace_id: str
    name: str
    started_at: datetime
    parent_span_id: str | None = None
    ended_at: datetime | None = None
    status: SpanStatus = SpanStatus.OK
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class Event:
    event_id: str
    event_name: str
    trace_id: str
    payload: Any
    emitted_at: datetime = field(default_factory=_now)
