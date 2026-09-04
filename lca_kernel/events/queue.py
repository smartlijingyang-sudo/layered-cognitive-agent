"""DeliveryQueue —— ADR-0184 PR-1 投递入队。

有界入队队列,生产者 ``submit()`` 立即返回。PR-2 会接
:class:`lca_kernel.events.persistence.PersistenceWorker` 消费;本 PR
仅提供入队与计数器投影,留 ``aiter()`` / ``mark_drained()`` 骨架。

设计要点(ADR-0184 §1):
- ``submit()`` 满了抛 :class:`DeliveryQueueFull` + 计数器自增 ——
  backpressure 暴露给上层(``/health.queue_depth`` / ``dropped``)。
- ``_pending_event_ids`` 跟踪入队未消费的 event_id;PR-2 worker
  消费完一条后调 :meth:`mark_drained` 移除。
- 计数 ``enqueued_total`` / ``dropped_queue_full`` 全局累计,不按
  category 区分(队列层看不到 category 投影)。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lca.contracts.event import EventPayload
    from lca_kernel.events.bus import EnvelopeRef


class DeliveryQueueFull(RuntimeError):
    """队列已满 — submit 抛此错;调用方负责降级或丢弃策略。

    ADR-0184 I2 D4 关联语义:strict=True 时事件不进 fanout;
    strict=False 时由 :class:`lca_kernel.events.bus.EventBus` 计入
    ``dropped`` 计数器,生产者继续返回。
    """

    def __init__(self, max_size: int) -> None:
        super().__init__(f"DeliveryQueue 已满(max_size={max_size});submit 拒绝")
        self.max_size = max_size


class DeliveryQueue:
    """有界入队队列。

    ``submit()`` 同步入队:满了抛 :class:`DeliveryQueueFull`,计数器
    ``dropped_queue_full`` 自增。``aiter()`` 留给 PR-2
    PersistenceWorker 消费;本 PR 留骨架,无 consumer 时入队事件永久
    留在队列里(不影响 EventBus 兼容性测试)。

    属性为只读快照,调用方可自由读取聚合,不触发额外入队。
    """

    def __init__(self, *, max_size: int = 10000) -> None:
        if max_size <= 0:
            raise ValueError(f"DeliveryQueue max_size 必须 > 0,got {max_size}")
        self._max_size = max_size
        self._queue: asyncio.Queue[tuple[EnvelopeRef, EventPayload]] = asyncio.Queue(
            maxsize=max_size
        )
        self._pending_event_ids: dict[str, EnvelopeRef] = {}
        self._lock = asyncio.Lock()
        self._enqueued_total = 0
        self._dropped_queue_full = 0

    @property
    def max_size(self) -> int:
        return self._max_size

    @property
    def depth(self) -> int:
        """当前在队事件数(未含已 mark_drained)。"""
        return self._queue.qsize()

    @property
    def pending_event_ids(self) -> dict[str, EnvelopeRef]:
        """event_id → EnvelopeRef 快照;PR-2 worker 用来追踪未消费项。"""
        return dict(self._pending_event_ids)

    @property
    def enqueued_total(self) -> int:
        """本队列累计入队事件数(含已消费)。"""
        return self._enqueued_total

    @property
    def dropped_queue_full(self) -> int:
        """本队列累计因 max_size 触顶被拒收的事件数。"""
        return self._dropped_queue_full

    def submit(self, ref: EnvelopeRef, payload: EventPayload) -> None:
        """入队一条事件。满了 → 抛 :class:`DeliveryQueueFull` + 计数器自增。

        注:asyncio.Queue.put_nowait 在已满时抛 QueueFull;本方法不把
        该异常透传,而是统一包装为 DeliveryQueueFull 以让上层错误处理
        单点化。submit 是 sync 方法 — 调用方在同步上下文(executor /
        boot 期)也可使用,与现有 EventBus.publish 同步签名一致。
        """
        try:
            self._queue.put_nowait((ref, payload))
        except asyncio.QueueFull as exc:
            self._dropped_queue_full += 1
            raise DeliveryQueueFull(max_size=self._max_size) from exc
        self._pending_event_ids[ref.event_id] = ref
        self._enqueued_total += 1

    async def aiter(self) -> AsyncIterator[tuple[EnvelopeRef, EventPayload]]:
        """PR-2 PersistenceWorker 消费入口。

        本 PR 不消费,留骨架以提示未来接法:``async for ref, payload in q.aiter(): ...``
        即可。运行期无 consumer 时 ``put_nowait`` 仍正常,事件卡在队列里。
        """
        while True:
            ref, payload = await self._queue.get()
            yield ref, payload

    def mark_drained(self, event_id: str) -> None:
        """PR-2 worker 消费完一条后调,从 ``_pending_event_ids`` 移除。

        重复调用同一 event_id 是 no-op(ProducerWorker 重试时常见)。
        Args:
            event_id: 已落盘事件的 EnvelopeRef.event_id。
        """
        self._pending_event_ids.pop(event_id, None)

    def __repr__(self) -> str:
        return (
            f"DeliveryQueue(max_size={self._max_size}, depth={self.depth}, "
            f"enqueued_total={self._enqueued_total}, "
            f"dropped_queue_full={self._dropped_queue_full})"
        )


__all__ = ["DeliveryQueue", "DeliveryQueueFull"]
