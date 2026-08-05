"""SpanView —— OTel ReadableSpan 的本地投影视图。

叙事渲染（console/jsonl/测试断言）只消费 ``SpanView``，不接触 OTel 类型；
骨干可替换性由此保证。字段与旧 TraceSpan 语义对齐，渲染层平移零改动。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from opentelemetry.trace import StatusCode


@dataclass(frozen=True)
class SpanView:
    """已完成 span 的只读视图。

    ``status`` 取值 ``"ok" | "error"``；``duration_ms`` 为整数毫秒。
    """

    name: str
    span_id: str
    trace_id: str
    parent_span_id: str | None
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"
    duration_ms: int = 0
    events: tuple[tuple[str, dict[str, Any]], ...] = ()


def view_of(readable_span: Any) -> SpanView:
    """OTel ReadableSpan → SpanView（仅在 L0 边界调用）。"""
    context = readable_span.context
    parent = readable_span.parent
    start = readable_span.start_time or 0
    end = readable_span.end_time or start
    status_obj = readable_span.status
    status = (
        "error" if status_obj is not None and status_obj.status_code == StatusCode.ERROR else "ok"
    )
    events = tuple((ev.name, dict(ev.attributes or {})) for ev in (readable_span.events or ()))
    return SpanView(
        name=readable_span.name,
        span_id=format(context.span_id, "016x"),
        trace_id=format(context.trace_id, "032x"),
        parent_span_id=format(parent.span_id, "016x") if parent is not None else None,
        attributes=dict(readable_span.attributes or {}),
        status=status,
        duration_ms=int((end - start) // 1_000_000),
        events=events,
    )
