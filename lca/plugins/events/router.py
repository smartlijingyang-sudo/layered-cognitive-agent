"""事件 v2 路由器 —— 按 category 找订阅者并 fanout（ADR-0179）。

路由职责：
- 按 ``Event.category`` 找出所有订阅该 category 的消费者；
- fanout 调用 ``consumer.on_event(event, ref)``；
- 消费者异常被捕获并写日志（不污染调用方；调用方拿到的永远是 ``EventRef``）。

本模块**不**校验 schema、不感知持久化、不感知后端 backend —— 那是 sender 与
消费者的职责。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from lca.contracts.event_v2 import Event, EventRef

if TYPE_CHECKING:
    from lca.plugins.events.consumer_registry import ConsumerRegistry

_log = logging.getLogger(__name__)


class EventRouterImpl:
    """事件路由器：category → 订阅者 fanout。

    注册中心通过 :class:`ConsumerRegistry` 注入；本路由器只读，不持有状态。
    """

    def __init__(self, registry: ConsumerRegistry) -> None:
        self._registry = registry

    def dispatch(self, event: Event, ref: EventRef) -> int:
        """按 category 派发事件；返回成功消费的消费者数量（用于自检）。"""
        consumers = self._registry.consumers_for(event.category)
        delivered = 0
        for consumer in consumers:
            try:
                consumer.on_event(event, ref)
                delivered += 1
            except Exception:
                # E8：消费者异常不能污染发送方；记日志，路由继续。
                _log.exception(
                    "EventRouter dispatch failed",
                    extra={
                        "event_id": ref.event_id,
                        "category": event.category.value,
                        "consumer": type(consumer).__name__,
                    },
                )
        return delivered


__all__ = ["EventRouterImpl"]
