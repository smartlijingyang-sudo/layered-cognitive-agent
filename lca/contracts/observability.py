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
    """OpenTelemetry 风格的追踪跨度。"""

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
    """不可变事实事件：记录某时刻发生的领域事件。"""

    event_id: str
    event_name: str
    trace_id: str
    payload: Any
    emitted_at: datetime = field(default_factory=_now)
