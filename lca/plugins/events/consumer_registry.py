"""事件 v2 消费者注册表（ADR-0179）。

注册表是路由器的查询后端：按 ``EventCategory`` 索引订阅者。

设计要点：
- 启动期由 profile 装载时构造（一次性注册）；
- 运行期**不**支持动态注销（防 race）；试点不暴露该能力。
"""

from __future__ import annotations

from collections import defaultdict

from lca.contracts.event_v2 import EventCategory
from lca.contracts.event_v2 import EventConsumerProtocol as EventConsumer


class ConsumerRegistry:
    """category → 消费者列表。"""

    def __init__(self) -> None:
        self._by_category: dict[EventCategory, list[EventConsumer]] = defaultdict(list)

    def register(self, consumer: EventConsumer) -> None:
        """注册一个消费者；同一消费者注册两次 = 重复订阅，需去重。"""
        categories = consumer.categories
        if not categories:
            msg = f"消费者 {type(consumer).__name__} 订阅集合为空"
            raise ValueError(msg)
        for category in categories:
            existing = self._by_category[category]
            if consumer not in existing:
                existing.append(consumer)

    def consumers_for(self, category: EventCategory) -> tuple[EventConsumer, ...]:
        """返回订阅该 category 的消费者；保持注册顺序。"""
        return tuple(self._by_category.get(category, ()))

    def all_categories(self) -> tuple[EventCategory, ...]:
        """返回至少有一个消费者的 category。"""
        return tuple(self._by_category.keys())


__all__ = ["ConsumerRegistry"]
