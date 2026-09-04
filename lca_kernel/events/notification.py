"""NotificationBus —— ADR-0184 PR-1 in-memory pubsub。

按 category 路由的轻量发布订阅层。``EnvelopeBus.publish`` 入队后
调 :meth:`NotificationBus.notify` 同步通知 observers(本 PR 兼容 shim
``EventBus`` 的 ``_fanout`` 也复用本协议);PR-3 扩
:meth:`subscribe_pull` 提供 AsyncIterator(供
:class:`lca_kernel.events.reader.SpineReader` 异步消费)。

设计要点(ADR-0184 §1):
- 同步 ``notify`` 与异步 ``subscribe_pull`` 双形态共存,正交:同步
  callback 适合 EventBus 兼容路径(立即 fire-and-forget),pull 形
  态供 PR-3 deriver 重连到 SpineReader(seek-by-seq 而非从头读)。
- 无消费者时 ``notify`` 为 no-op,不抛错;不阻塞 publish 主路径。
- category 接受 :class:`lca.contracts.event.Category` 或字符串
  ``Category.value``;key 一律取 ``str()`` 归一。
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lca.contracts.event import Category, EventPayload
    from lca_kernel.events.bus import EnvelopeRef


NotificationCallback = Callable[["EnvelopeRef", "EventPayload"], None]
"""同步回调签名:envelope_ref + payload,caller 自行处理;失败吞错。"""


def _category_key(category: Category | str) -> str:
    """统一 category key:``Category`` 取 ``.value``,字符串原样。"""
    return category.value if hasattr(category, "value") else str(category)


class NotificationBus:
    """按 category 路由的 in-memory pubsub。

    本 PR 提供 sync ``notify`` / ``subscribe`` + skeleton ``subscribe_pull``;
    PR-3 在 Subscribe_pull 内接 SpineReader 并暴露
    :class:`lca_kernel.events.reader.SpineReader` 异步事件流。
    """

    def __init__(self) -> None:
        self._observers: dict[str, list[NotificationCallback]] = defaultdict(list)
        self._async_queues: dict[str, list[asyncio.Queue[tuple[EnvelopeRef, EventPayload]]]] = (
            defaultdict(list)
        )

    def subscribe(self, category: Category | str, callback: NotificationCallback) -> None:
        """注册同步 callback。失败由 callback 自身吞错,bus 不传递。

        同一 callback 注册多次 → 派发多次(允许 fan-out);重复保护
        由 caller 自行负责。
        """
        self._observers[_category_key(category)].append(callback)

    def observer_count(self, category: Category | str) -> int:
        """某 category 注册的同步 callback 数。"""
        return len(self._observers.get(_category_key(category), ()))

    def notify(self, ref: EnvelopeRef, payload: EventPayload) -> None:
        """同步通知该 category 的 observers。

        无 callback → no-op。
        callback 抛错 → exception 透传(EventBus 兼容 shim 用 ``_fanout``
        路径已经处理 ``FAIL_FAST`` / ``CONTAINED`` 语义,本层只负责分发)。
        """
        for callback in self._observers.get(_category_key(payload.category), ()):
            callback(ref, payload)

    async def subscribe_pull(
        self, category: Category | str
    ) -> AsyncIterator[tuple[EnvelopeRef, EventPayload]]:
        """PR-3 用异步 pull 形态。本 PR 仅注册一个内部队列并 yield。

        当前实现为内存内 push-to-pull 桥(no-op 转换);PR-3 替换为
        ``SpineReader`` seek-by-seq 实现,docstring 与行为不兼容本骨架。
        """
        key = _category_key(category)
        queue: asyncio.Queue[tuple[EnvelopeRef, EventPayload]] = asyncio.Queue(maxsize=1024)
        self._async_queues[key].append(queue)
        while True:
            ref, payload = await queue.get()
            yield ref, payload

    @property
    def categories(self) -> tuple[str, ...]:
        """所有注册过 callback 的 category key 列表(只读快照)。"""
        return tuple(self._observers.keys())

    def __repr__(self) -> str:
        categories = ", ".join(sorted(self._observers.keys())) or "<none>"
        return f"NotificationBus(categories=[{categories}], observers_per_cat={ {k: len(v) for k, v in self._observers.items()} })"


__all__ = ["NotificationBus", "NotificationCallback"]
