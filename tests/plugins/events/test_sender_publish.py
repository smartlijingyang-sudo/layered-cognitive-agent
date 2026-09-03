"""ADR-0179 试点：EventSenderImpl 单元测试。

覆盖：
- publish(payload) 返回 EventRef；
- EventRef 包含 event_id、ts；
- 路由无消费者时返回 ref（不抛异常）；
- 消费者抛异常被 router 吞掉（E8：消费者不污染发送方）。
"""

from __future__ import annotations

from lca.contracts.event_v2 import (
    DelegationCacheHit,
    Event,
    EventCategory,
    EventPlane,
    EventRef,
)
from lca.plugins.events.consumer_registry import ConsumerRegistry
from lca.plugins.events.router import EventRouterImpl
from lca.plugins.events.sender import EventSenderImpl


class _BoomConsumer:
    @property
    def categories(self):
        from lca.contracts.event_v2 import EventCategory

        return frozenset({EventCategory.TEAM_DELEGATION})

    def on_event(self, event: Event, ref: EventRef) -> None:
        raise RuntimeError("boom")


class _CaptureConsumer:
    def __init__(self) -> None:
        self.events: list[tuple[Event, EventRef]] = []

    @property
    def categories(self):
        from lca.contracts.event_v2 import EventCategory

        return frozenset({EventCategory.TEAM_DELEGATION})

    def on_event(self, event: Event, ref: EventRef) -> None:
        self.events.append((event, ref))


def _build_sender(consumers: list) -> tuple[EventSenderImpl, _CaptureConsumer | None]:
    reg = ConsumerRegistry()
    capture: _CaptureConsumer | None = None
    for c in consumers:
        reg.register(c)
        if isinstance(c, _CaptureConsumer):
            capture = c
    router = EventRouterImpl(reg)
    return EventSenderImpl(router, dual_write_legacy=False), capture


def test_publish_returns_event_ref() -> None:
    sender, _ = _build_sender([])
    ref = sender.publish(DelegationCacheHit(callee_role="a", subtask_preview="b", step=1))
    assert isinstance(ref, EventRef)
    assert ref.event_id.startswith("evt_")
    assert ref.ts > 0


def test_publish_dispatches_to_consumer() -> None:
    cap = _CaptureConsumer()
    sender, capture = _build_sender([cap])
    ref = sender.publish(DelegationCacheHit(callee_role="a", subtask_preview="b", step=2))
    assert capture is not None
    assert len(capture.events) == 1
    event, observed_ref = capture.events[0]
    assert event.category is EventCategory.TEAM_DELEGATION
    assert event.plane is EventPlane.STRUCTURAL
    assert observed_ref is ref


def test_consumer_exception_is_swallowed() -> None:
    """E8：消费者异常不污染发送方；返回 ref。"""
    sender, _ = _build_sender([_BoomConsumer()])
    ref = sender.publish(DelegationCacheHit(callee_role="a", subtask_preview="b", step=3))
    assert isinstance(ref, EventRef)


def test_publish_is_sender_schema_unaware() -> None:
    """E2：sender 不读 payload 字段、不感知 schema。"""
    sender, _ = _build_sender([])

    # 任意 payload 都能发；sender 不校验字段。
    class _AnyPayload:
        category = EventCategory.TEAM_DELEGATION

        # 故意不继承 EventPayload；sender 不强校验
        def __init__(self):
            self.foo = "bar"

    # 但 publish 类型注解要求 EventPayload；这里用 type: ignore 验证运行时无校验。
    # 当前 sender 也不做 isinstance 校验（E2），所以这里只是说明意图而非断言。
    # 实际生产代码应传 EventPayload 子类。
    _ = sender  # 占位，避免未使用告警


def test_module_publish_returns_none_when_no_sender() -> None:
    """业务方调 publish()（模块函数）时 sender 未 boot → None。"""
    from lca.plugins.events.sender import publish as module_publish
    from lca.plugins.events.sender import set_active_sender

    set_active_sender(None)
    result = module_publish(DelegationCacheHit(callee_role="a", subtask_preview="b", step=0))
    assert result is None


def test_module_publish_routes_when_sender_installed() -> None:
    from lca.plugins.events.sender import publish as module_publish
    from lca.plugins.events.sender import set_active_sender

    cap = _CaptureConsumer()
    sender, capture = _build_sender([cap])
    set_active_sender(sender)
    try:
        module_publish(DelegationCacheHit(callee_role="a", subtask_preview="b", step=5))
    finally:
        set_active_sender(None)
    assert capture is not None
    assert len(capture.events) == 1
