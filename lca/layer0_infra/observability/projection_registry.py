"""事件账本投影注册表。

账本只提交事件；所有 JSONL、控制台、SSE、OTel、Langfuse 和诊断视图都由本
注册表在提交后单向消费。投影失败只产生进程运维日志，绝不回写事件账本或中断
Agent 运行。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

import structlog

from lca.contracts.models.observability.journal import StampedEvent

_log = structlog.get_logger("lca.observability.projections")


@runtime_checkable
class EventProjection(Protocol):
    """一个只读的事件账本投影。"""

    def on_event(self, event: StampedEvent) -> None:
        """消费已经提交的事件。"""
        ...


class ProjectionRegistry:
    """按装配顺序分发事件，并隔离每个投影器的失败。"""

    def __init__(self, projections: Sequence[EventProjection] = ()) -> None:
        self._projections = tuple(projections)
        self._closed = False

    @property
    def projections(self) -> tuple[EventProjection, ...]:
        return self._projections

    def publish(self, event: StampedEvent) -> None:
        if self._closed:
            return
        for projection in self._projections:
            try:
                projection.on_event(event)
            except Exception:
                _log.warning(
                    "event_projection_failed",
                    projection=type(projection).__name__,
                    event_type=event.event_type,
                    seq=event.seq,
                )

    def flush(self) -> None:
        """冲刷支持缓冲的投影；纯投影无需实现该可选能力。"""
        for projection in self._projections:
            flush = getattr(projection, "flush", None)
            if not callable(flush):
                continue
            try:
                flush()
            except Exception:
                _log.warning("event_projection_flush_failed", projection=type(projection).__name__)

    def close(self) -> None:
        """停止投影；重复调用安全。"""
        if self._closed:
            return
        self._closed = True
        self.flush()
        for projection in self._projections:
            close = getattr(projection, "close", None)
            if not callable(close):
                continue
            try:
                close()
            except Exception:
                _log.warning("event_projection_close_failed", projection=type(projection).__name__)


__all__ = ["EventProjection", "ProjectionRegistry"]
