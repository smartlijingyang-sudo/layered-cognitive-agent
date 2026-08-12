"""EventStream — 事件分发原语。

环形缓冲 + 发布/订阅 + 断线回放。不知道 Journal / SSE / LobeHub 是什么。

替代旧架构中 EventBus + EventBusProjector + ObservabilityHub 的三层间接层。
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass

import structlog

from lca.contracts.models.observability.journal import StampedEvent

_log = structlog.get_logger(__name__)

_MAX_BUFFERED: int = 4096
_MAX_QUEUE: int = 256
_OVERFLOW_THRESHOLD: int = 3


@dataclass(frozen=True, slots=True)
class GapEvent:
    """subscribe() 检测到 after_seq 已被环形缓冲淘汰时 yield 的信号。

    消费侧收到后可决定是否回退到 JSONL 重放。
    不是 StampedEvent 的子类——它是一个控制信号，不是领域事件。
    """

    requested_seq: int
    oldest_available_seq: int


@dataclass(slots=True)
class _Subscriber:
    """单个订阅者的运行时状态。

    overflow_count 可变（非 frozen），因为 publish 需要原地更新。
    """

    queue: asyncio.Queue[StampedEvent | None]
    overflow_count: int = 0


class EventStream:
    """事件分发原语。不知道 Journal、SSE、LobeHub。

    职责边界：
      - 环形缓冲（有界内存，back-pressure 通过丢弃最老事件实现）
      - 发布/订阅（多消费者广播）
      - 断线回放（after_seq），原子化注册+回放，无竞态窗口
      - Buffer gap 检测（after_seq 被淘汰时发 GapEvent）
      - 关闭信号（run 结束）

    不做的事：
      - 不做事件过滤（过滤在 TimelineProjection 层）
      - 不做序列化（编码在 SSE adapter 层）
      - 不做格式转换（投影在 Projection 层）
    """

    __slots__ = ("_closed", "_frames", "_subscribers")

    def __init__(self) -> None:
        self._frames: deque[StampedEvent] = deque(maxlen=_MAX_BUFFERED)
        self._subscribers: list[_Subscriber] = []
        self._closed: bool = False

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def subscriber_count(self) -> int:
        """暴露给观测端点。"""
        return len(self._subscribers)

    @property
    def buffer_size(self) -> int:
        """暴露给观测端点。"""
        return len(self._frames)

    def publish(self, stamped: StampedEvent) -> None:
        """广播到所有活跃订阅者。

        溢出策略：
          - 单次 queue full：记 warning 日志 + overflow_count++，不移除
          - 连续溢出 >= _OVERFLOW_THRESHOLD 次：记 error 日志 + 移除
          - 成功投递：overflow_count 归零
        """
        if self._closed:
            return
        self._frames.append(stamped)

        dead: list[int] = []
        for idx, sub in enumerate(self._subscribers):
            try:
                sub.queue.put_nowait(stamped)
                sub.overflow_count = 0
            except asyncio.QueueFull:
                sub.overflow_count += 1
                if sub.overflow_count >= _OVERFLOW_THRESHOLD:
                    dead.append(idx)
                    _log.error(
                        "event_stream_subscriber_evicted",
                        consecutive_overflows=sub.overflow_count,
                        queue_size=_MAX_QUEUE,
                        seq=stamped.seq,
                    )
                else:
                    _log.warning(
                        "event_stream_subscriber_overflow",
                        overflow_count=sub.overflow_count,
                        queue_utilization=sub.queue.qsize() / _MAX_QUEUE,
                        threshold=_OVERFLOW_THRESHOLD,
                        queue_size=_MAX_QUEUE,
                        seq=stamped.seq,
                    )
        for idx in reversed(dead):
            self._subscribers.pop(idx)

    def register_subscriber(self, queue: asyncio.Queue[StampedEvent | None]) -> None:
        """同步注册一个 subscriber queue。

        供需要在 publish 前确保注册的场景使用（如 JSONL consumer）。
        注册后 queue 会收到后续所有 publish 的事件，以及 close() 时的 sentinel。
        """
        self._subscribers.append(_Subscriber(queue=queue))

    async def subscribe(self, after_seq: int = 0) -> AsyncIterator[StampedEvent | GapEvent]:
        """原子化订阅：注册队列 → 回放缓冲 → 流式 live。

        返回类型：AsyncIterator[StampedEvent | GapEvent]
          - 首条可能是 GapEvent（缓冲已淘汰 after_seq 之前的事件）
          - 后续全部是 StampedEvent
          - 调用者需要用 isinstance(item, GapEvent) 区分

        关键：注册发生在回放之前，因此回放期间 publish 的事件
        不会丢失——它们会进入已注册的 queue，在回放结束后被消费。
        """
        queue: asyncio.Queue[StampedEvent | None] = asyncio.Queue(_MAX_QUEUE)
        sub = _Subscriber(queue=queue)
        self._subscribers.append(sub)

        oldest_seq = self._frames[0].seq if self._frames else None
        if oldest_seq is not None and after_seq < oldest_seq:
            yield GapEvent(
                requested_seq=after_seq,
                oldest_available_seq=oldest_seq,
            )

        replay_count = 0
        for stamped in self._frames:
            if stamped.seq > after_seq:
                yield stamped
                replay_count += 1
                if replay_count % 64 == 0:
                    await asyncio.sleep(0)

        # If the stream was closed during replay (or before subscribe),
        # all buffered events have been yielded — no sentinel will arrive.
        if self._closed:
            return

        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if item.seq > after_seq:
                    yield item
        finally:
            self._subscribers = [s for s in self._subscribers if s.queue is not queue]

    def buffered_after(self, after_seq: int = 0) -> list[StampedEvent]:
        """非阻塞快照：返回 seq > after_seq 的缓冲事件。仅供调试端点使用。"""
        return [s for s in self._frames if s.seq > after_seq]

    def close(self) -> None:
        """发送 sentinel，通知所有订阅者流结束。

        幂等：已经 close 过则立即返回。
        异常保护：queue 已满时强制清空一个位置后投递 sentinel。
        """
        if self._closed:
            return
        self._closed = True
        for sub in self._subscribers:
            try:
                sub.queue.put_nowait(None)
            except asyncio.QueueFull:
                sub.queue.get_nowait()
                sub.queue.put_nowait(None)
        self._subscribers.clear()
