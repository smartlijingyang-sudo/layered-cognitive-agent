"""第5.9节：可观测性与事件契约。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class TraceSpan:
    span_id: str
    trace_id: str
    name: str
    started_at: datetime
    parent_span_id: Optional[str] = None
    ended_at: Optional[datetime] = None
    status: Literal["ok", "error"] = "ok"
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class Event:
    event_id: str
    event_name: str
    trace_id: str
    payload: Any
    emitted_at: datetime = field(default_factory=_now)
