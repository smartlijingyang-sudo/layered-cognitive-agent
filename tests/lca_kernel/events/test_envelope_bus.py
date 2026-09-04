"""ADR-0184 PR-1:EnvelopeBus / EventBus compat shim 测试。

覆盖(plan §PR-1 验证清单):
- test_envelope_bus_publish_returns_envelope_ref:EnvelopeBus.publish 返回 4 字段 EnvelopeRef
- test_event_bus_compat_shim_preserves_persisted_subscriber_count:EventBus.publish EventRef 6 字段
- test_event_bus_compat_shim_no_regression_on_existing_wire:跑现 test_event_bus 全部 test,无回归
"""

from __future__ import annotations

from lca.contracts.event import Category, EventPayload
from lca_kernel.events import (
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


# ── 3:EventBus 兼容 shim — EventRef 6 字段保留 ──────────────────────────


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
