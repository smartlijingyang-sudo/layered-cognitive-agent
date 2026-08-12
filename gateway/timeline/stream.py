"""Stream helpers for timeline.v1 SSE — 唯一的 SSE 流组装点。

Pipeline 可组合：
  - 默认组装：TimelineProjection → LobeHubSSEAdapter → encode_sse
  - Raw 模式（调试端点）：跳过 adapter，直接 encode 领域事件
  - 自定义前端：传入自定义 adapter 替换 LobeHubSSEAdapter
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import structlog

from gateway.event_stream import EventStream, GapEvent
from gateway.timeline.lobehub_adapter import LobeHubSSEAdapter
from gateway.timeline.projection import TimelineProjection
from gateway.timeline.sse_encode import encode_sse
from lca.contracts.models.observability.journal import StampedEvent

_log = structlog.get_logger(__name__)


async def compose_sse_stream(
    stream: EventStream,
    *,
    after_seq: int = 0,
    projection: TimelineProjection | None = None,
    adapter: LobeHubSSEAdapter | None = None,
) -> AsyncIterator[bytes]:
    """唯一的 SSE 流组装点。

    被 /v1/agent/runs/{id}/timeline 和所有其他 SSE endpoint 调用。

    组装顺序：
      1. subscribe()（原子化注册 + 回放 + live）
      2. 投影（TimelineProjection）
      3. 适配（SSEAdapter）
      4. 编码（encode_sse）
    """
    proj = projection or TimelineProjection()
    adap = adapter or LobeHubSSEAdapter()

    async for item in stream.subscribe(after_seq=after_seq):
        if isinstance(item, GapEvent):
            yield encode_sse(
                {
                    "type": "reconnect.gap",
                    "requested_seq": item.requested_seq,
                    "oldest_available_seq": item.oldest_available_seq,
                },
                seq=item.oldest_available_seq,
                event_type="reconnect.gap",
            )
            continue
        for domain_event in proj.project(item):
            for payload in adap.adapt(domain_event):
                yield encode_sse(
                    payload,
                    seq=domain_event.seq,
                    event_type=domain_event.type,
                )


def project_all(stamped_events: list[StampedEvent]) -> list[dict[str, Any]]:
    """Synchronous project for tests / fixtures — 返回领域事件 dict 列表。"""
    proj = TimelineProjection()
    adap = LobeHubSSEAdapter()
    out: list[dict[str, Any]] = []
    for s in stamped_events:
        for domain_event in proj.project(s):
            for payload in adap.adapt(domain_event):
                payload.setdefault("seq", domain_event.seq)
                out.append(payload)
    return out
