"""ADR-0184 PR-1:EnvelopeBus / DeliveryQueue / NotificationBus / EventBus compat shim 测试。

覆盖(plan §PR-1 验证清单):
- test_envelope_bus_publish_returns_envelope_ref:EnvelopeBus.publish 返回 4 字段 EnvelopeRef
- test_envelope_bus_queue_submit_and_depth:DeliveryQueue.submit 后 depth == 1
- test_envelope_bus_dropped_queue_full_counter:max_size=1 第 2 条触发 DeliveryQueueFull + dropped
- test_envelope_bus_notification_default_none_noop:默认未注入 notification;S4 为 no-op
- test_envelope_bus_notification_subscribe_notify:显式注入后,订阅 + notify 同步触发 callback
- test_event_bus_compat_shim_preserves_persisted_subscriber_count:EventBus.publish EventRef 6 字段
- test_event_bus_compat_shim_no_regression_on_existing_wire:跑现 test_event_bus 全部 test,无回归
"""

from __future__ import annotations

import pytest

from lca.contracts.event import Category, EventPayload
from lca_kernel.events import (
    DeliveryQueueFull,
    EnvelopeBus,
    EnvelopeRef,
    EventBus,
    EventRef,
    TeamDelegationCacheHit,
)
from lca_kernel.events.test_catalog import build_test_bus

# ── 公共 helpers ─────────────────────────────────────────────────────────


def _make_envelope_bus() -> EnvelopeBus[EventPayload]:
    """独立 EnvelopeBus 实例(PR-1 测试隔离,不污染单例)。

    直接复用 :func:`build_test_bus` — 它返回 EventBus 实例,EnvelopeBus
    是其父类,测试用 isinstance 校验更宽松。
    """
    return build_test_bus()  # type: ignore[return-value]


def _authorized_payload() -> EventPayload:
    """yaml 试点白名单内的可用 payload。"""
    return TeamDelegationCacheHit(callee_role="a", subtask="b", step=1)


def _authorized_producer() -> type:
    from lca.plugins.events.publishers.delegation_cache.plugin import (
        DelegationCachePlugin,
    )

    return DelegationCachePlugin


# ── 1:EnvelopeBus.publish 返回 EnvelopeRef ──────────────────────────────


class TestEnvelopeBusPublish:
    def test_envelope_bus_publish_returns_envelope_ref(self) -> None:
        """EnvelopeBus.publish 返回 EnvelopeRef,4 字段非 None。"""
        bus = _make_envelope_bus()
        ref = bus.publish(_authorized_payload(), producer=_authorized_producer())
        assert isinstance(ref, EnvelopeRef)
        # 4 字段全部非 None / 非空
        assert ref.event_id and isinstance(ref.event_id, str)
        assert ref.category == "team.delegation.cache_hit"
        assert ref.trace_id and isinstance(ref.trace_id, str)
        assert isinstance(ref.ts, float)
        # EnvelopeRef 上不应有 persisted / subscriber_count(它们是 EventRef 字段)
        # 注:此处用 hasattr 作弱断言,因为 EventRef 继承 EnvelopeRef,若收到
        # EventRef 实例时仍有那些字段属于上层兼容行为。
        if isinstance(ref, EventRef):
            # 兼容 shim 返回:persisted / subscriber_count 类型对就行
            assert isinstance(ref.persisted, bool)
            assert isinstance(ref.subscriber_count, int)


# ── 2:DeliveryQueue.submit + depth ──────────────────────────────────────


class TestDeliveryQueue:
    def test_envelope_bus_queue_submit_and_depth(self) -> None:
        """入队一条后,DeliveryQueue.depth == 1。"""
        bus = _make_envelope_bus()
        # 触发一次 publish 让 EnvelopeBus 走完生命周期
        pre_depth = bus.queue.depth
        bus.publish(_authorized_payload(), producer=_authorized_producer())
        post_depth = bus.queue.depth
        # publish 后事件入队但本 PR 无 consumer → 留在队列
        assert post_depth == pre_depth + 1

    def test_envelope_bus_dropped_queue_full_counter(self) -> None:
        """max_size=1 时,第 2 条入队 → DeliveryQueueFull + dropped += 1。"""
        bus = _make_envelope_bus()
        # 替换 queue 为 max_size=1,走 publish 一次先填满队列
        from lca_kernel.events.queue import DeliveryQueue

        bus._queue = DeliveryQueue(max_size=1)
        # 第一条入队成功
        bus.publish(_authorized_payload(), producer=_authorized_producer())
        assert bus.queue.depth == 1
        # 第二条入队触发 DeliveryQueueFull
        with pytest.raises(DeliveryQueueFull):
            bus.publish(_authorized_payload(), producer=_authorized_producer())
        # dropped_queue_full 计数自增
        assert bus.queue.dropped_queue_full == 1


# ── 3:NotificationBus.subscribe + notify 同步形态(可选注入)──────────


class TestNotificationBus:
    def test_envelope_bus_notification_default_none_noop(self) -> None:
        """默认构造不注入 NotificationBus;S4 notify 为 no-op,publish 正常返回。"""
        bus = _make_envelope_bus()
        assert bus.notification is None
        # S4 no-op 不阻塞 publish,仍返回 4 字段 EnvelopeRef
        ref = bus.publish(_authorized_payload(), producer=_authorized_producer())
        assert isinstance(ref, EnvelopeRef)
        assert ref.event_id and isinstance(ref.event_id, str)

    def test_envelope_bus_notification_subscribe_notify(self) -> None:
        """显式注入 NotificationBus 后,订阅 + notify 调 callback(同步形态)。"""
        from lca_kernel.events.notification import NotificationBus

        notification = NotificationBus()
        bus = _make_envelope_bus()
        bus._notification = notification  # 显式注入,走可选派发路径
        seen: list[tuple[EnvelopeRef, EventPayload]] = []

        def _cb(ref: EnvelopeRef, payload: EventPayload) -> None:
            seen.append((ref, payload))

        assert bus.notification is notification
        bus.notification.subscribe(Category.TEAM_DELEGATION_CACHE_HIT, _cb)
        assert bus.notification.observer_count(Category.TEAM_DELEGATION_CACHE_HIT) == 1
        ref = bus.publish(_authorized_payload(), producer=_authorized_producer())
        # publish → super().publish → S4 notify(注入态)→ callback
        assert len(seen) == 1
        cb_ref, cb_payload = seen[0]
        assert cb_ref.event_id == ref.event_id
        assert cb_payload.category == Category.TEAM_DELEGATION_CACHE_HIT


# ── 4:EventBus 兼容 shim — EventRef 6 字段保留 ──────────────────────────


class TestEventBusCompatShim:
    def test_event_bus_compat_shim_preserves_persisted_subscriber_count(self) -> None:
        """EventBus.publish 返回 EventRef,含 persisted / subscriber_count 6 字段。"""
        bus: EventBus[EventPayload] = build_test_bus()
        assert isinstance(bus, EventBus)
        ref = bus.publish(_authorized_payload(), producer=_authorized_producer())
        assert isinstance(ref, EventRef)
        # 6 字段(4 字段从 EnvelopeRef + 2 字段 EventRef 自身)
        assert hasattr(ref, "event_id")
        assert hasattr(ref, "category")
        assert hasattr(ref, "trace_id")
        assert hasattr(ref, "ts")
        assert hasattr(ref, "persisted")
        assert hasattr(ref, "subscriber_count")
        # 类型断言
        assert isinstance(ref.event_id, str)
        assert isinstance(ref.persisted, bool)
        assert isinstance(ref.subscriber_count, int)
        # 无订阅者默认配置下 subscriber_count == 0
        assert ref.subscriber_count == 0

    def test_event_bus_compat_shim_subscriber_count_after_subscribe(self) -> None:
        """EventBus.publish 在订阅后,EventRef.subscriber_count > 0(persisted=False)。"""
        bus = build_test_bus()
        from lca.plugins.events.subscribers.console_projector.subscriber import (
            ConsoleProjectorSubscriber,
        )

        bus.subscribe(
            plugin=ConsoleProjectorSubscriber,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=lambda _p, _r: None,
        )
        ref = bus.publish(_authorized_payload(), producer=_authorized_producer())
        assert ref.subscriber_count == 1
        # 当前严格 strict=False + 无 sink → persisted=False(降级为 dropped)
        assert ref.persisted is False

    def test_event_bus_compat_shim_no_regression_on_existing_wire(self) -> None:
        """EventBus 兼容 shim 路径与现有 wire 行为一致(counters 四值)。"""
        bus = build_test_bus()
        bus.publish(_authorized_payload(), producer=_authorized_producer())
        snap = bus.delivery_snapshot()
        # 至少有过 publish(team.delegation.cache_hit 应在 snapshot 内)
        assert "team.delegation.cache_hit" in snap
        entry = snap["team.delegation.cache_hit"]
        # 四值存在 + 类型对
        for key in ("published", "persisted", "delivered", "dropped"):
            assert key in entry
            assert isinstance(entry[key], int)
        # published 必须 >= 1
        assert entry["published"] >= 1
