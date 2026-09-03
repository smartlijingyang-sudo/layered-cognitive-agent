"""ADR-0179 试点：ConsumerRegistry + Router 订阅路由测试。

覆盖：
- 消费者按 category 订阅；按 category 查询返回对应消费者；
- 同一消费者订阅多 category 时全部分发；
- 订阅全量（frozenset(EventCategory)）时任何 category 都收到；
- 路由无消费者时 dispatch 返回 0，不抛异常。
"""

from __future__ import annotations

from lca.contracts.event_v2 import Event, EventCategory, EventRef
from lca.plugins.events.consumer_registry import ConsumerRegistry
from lca.plugins.events.router import EventRouterImpl


class _SelectiveConsumer:
    def __init__(self, *categories: EventCategory):
        self._cats = frozenset(categories)
        self.received: list[tuple[Event, EventRef]] = []

    @property
    def categories(self):
        return self._cats

    def on_event(self, event, ref):
        self.received.append((event, ref))


def test_consumer_subscribed_by_category() -> None:
    reg = ConsumerRegistry()
    c = _SelectiveConsumer(EventCategory.TEAM_DELEGATION)
    reg.register(c)
    assert reg.consumers_for(EventCategory.TEAM_DELEGATION) == (c,)
    assert reg.consumers_for(EventCategory.TOOL) == ()


def test_consumer_multi_category() -> None:
    reg = ConsumerRegistry()
    c = _SelectiveConsumer(EventCategory.TEAM_DELEGATION, EventCategory.GATE)
    reg.register(c)
    assert reg.consumers_for(EventCategory.TEAM_DELEGATION) == (c,)
    assert reg.consumers_for(EventCategory.GATE) == (c,)
    assert reg.consumers_for(EventCategory.TOOL) == ()


def test_consumer_all_categories_subscribes_to_anything() -> None:
    reg = ConsumerRegistry()
    c = _SelectiveConsumer(*EventCategory)
    reg.register(c)
    for cat in EventCategory:
        assert reg.consumers_for(cat) == (c,)


def test_router_dispatches_to_correct_consumer() -> None:
    reg = ConsumerRegistry()
    c_delegation = _SelectiveConsumer(EventCategory.TEAM_DELEGATION)
    c_tool = _SelectiveConsumer(EventCategory.TOOL)
    reg.register(c_delegation)
    reg.register(c_tool)
    router = EventRouterImpl(reg)

    event = Event(
        category=EventCategory.TEAM_DELEGATION,
        plane=__import__("lca.contracts.event_v2", fromlist=["EventPlane"]).EventPlane.STRUCTURAL,
        payload=__import__(
            "lca.contracts.event_v2", fromlist=["DelegationCacheHit"]
        ).DelegationCacheHit(callee_role="x", subtask_preview="y", step=0),
    )
    ref = EventRef(event_id="e1", trace_id="", ts=0.0)
    delivered = router.dispatch(event, ref)
    assert delivered == 1
    assert len(c_delegation.received) == 1
    assert len(c_tool.received) == 0


def test_router_dispatch_with_no_consumers_returns_zero() -> None:
    reg = ConsumerRegistry()
    router = EventRouterImpl(reg)
    event = Event(
        category=EventCategory.GATE,
        plane=__import__("lca.contracts.event_v2", fromlist=["EventPlane"]).EventPlane.STRUCTURAL,
        payload=__import__(
            "lca.contracts.event_v2", fromlist=["DelegationCacheHit"]
        ).DelegationCacheHit(callee_role="x", subtask_preview="y", step=0),
    )
    ref = EventRef(event_id="e2", trace_id="", ts=0.0)
    assert router.dispatch(event, ref) == 0


def test_register_rejects_duplicate_consumer() -> None:
    reg = ConsumerRegistry()
    c = _SelectiveConsumer(EventCategory.TEAM_DELEGATION)
    reg.register(c)
    reg.register(c)  # 同一消费者注册两次
    consumers = reg.consumers_for(EventCategory.TEAM_DELEGATION)
    assert consumers.count(c) == 1


def test_register_rejects_empty_categories() -> None:
    reg = ConsumerRegistry()

    class _Empty:
        @property
        def categories(self):
            return frozenset()

        def on_event(self, event, ref):
            pass

    import pytest

    with pytest.raises(ValueError, match="订阅集合为空"):
        reg.register(_Empty())
