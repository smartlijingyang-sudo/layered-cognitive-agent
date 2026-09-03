"""PR-12 机制自观察(§3.10)单元测试。

覆盖:
- MechanismDispatchObserver 按失败语义拆 sinks / consumers 两阶段派生
- 自观察事件继承被观察事件 trace_id
- 防递归守卫:自观察事件不重入 post_dispatch、不进业务订阅
- MechanismDispatchEventPayload category 字符串闭集校验
- subscribe_self_observation 闭集外拒绝
"""

from __future__ import annotations

import pytest

from lca.contracts.event import Category, EventPayload
from lca_kernel.events import TeamDelegationCacheHit
from lca_kernel.events.bus import EventBus, FailureSemantics, reset_trace_id, set_trace_id
from lca_kernel.events.errors import MissingPluginIdentityError, UnauthorizedSubscribeError
from lca_kernel.events.hooks import MechanismDispatchObserver
from lca_kernel.events import EventRef, _DEFAULT_CONFIG_DIR
from lca_kernel.events.payloads import (
    DISPATCH_SELF_OBSERVATION_CATEGORIES,
    MechanismDispatchEventPayload,
)
from lca_kernel.events.pipeline import HookSpec, Pipeline, Stage
from lca_kernel.events.registry import EventRegistry

SINKS_END = "event.bus.dispatch.sinks.end"
CONSUMERS_END = "event.bus.dispatch.consumers.end"


def _make_bus() -> EventBus[EventPayload]:
    registry = EventRegistry.load(_DEFAULT_CONFIG_DIR)
    return EventBus(registry)


@pytest.fixture
def bus() -> EventBus[EventPayload]:
    return _make_bus()


@pytest.fixture
def authorized_plugin() -> type:
    from lca.plugins.events.publishers.delegation_cache.plugin import (
        DelegationCachePlugin,
    )

    return DelegationCachePlugin


@pytest.fixture
def subscriber_plugin() -> type:
    from lca.plugins.events.subscribers.console_projector.subscriber import (
        ConsoleProjectorSubscriber,
    )

    return ConsoleProjectorSubscriber


@pytest.fixture
def payload() -> TeamDelegationCacheHit:
    return TeamDelegationCacheHit(callee_role="a", subtask="b", step=1)


def _install_observer(bus: EventBus[EventPayload]) -> None:
    bus.register_pipeline(
        Pipeline(
            name="t",
            hooks=(HookSpec(id="obs", hook=MechanismDispatchObserver, stage=Stage.POST_DISPATCH),),
        )
    )


def _capture(bus: EventBus[EventPayload]) -> list[tuple[MechanismDispatchEventPayload, EventRef]]:
    """注册两个自观察消费者,收集 (payload, ref)。"""
    captured: list[tuple[MechanismDispatchEventPayload, EventRef]] = []
    for cat in (SINKS_END, CONSUMERS_END):
        bus.subscribe_self_observation(
            plugin=object,
            category=cat,
            on_event=lambda p, r: captured.append((p, r)),
        )
    return captured


# ── payload 闭集 ────────────────────────────────────────────────────────


class TestPayloadClosedSet:
    def test_valid_categories(self) -> None:
        for cat in DISPATCH_SELF_OBSERVATION_CATEGORIES:
            p = MechanismDispatchEventPayload(category=cat, consumer_count=1, duration_s=0.0)
            assert p.category == cat

    def test_unknown_category_rejected(self) -> None:
        with pytest.raises(ValueError):
            MechanismDispatchEventPayload(category="bogus.cat", consumer_count=0, duration_s=0.0)

    def test_negative_count_rejected(self) -> None:
        with pytest.raises(ValueError):
            MechanismDispatchEventPayload(category=SINKS_END, consumer_count=-1, duration_s=0.0)


# ── subscribe_self_observation ──────────────────────────────────────────


class TestSubscribeSelfObservation:
    def test_reject_outside_closed_set(self, bus: EventBus[EventPayload]) -> None:
        with pytest.raises(UnauthorizedSubscribeError):
            bus.subscribe_self_observation(
                plugin=object, category="not.dispatch.cat", on_event=lambda p, r: None
            )

    def test_reject_missing_plugin(self, bus: EventBus[EventPayload]) -> None:
        with pytest.raises(MissingPluginIdentityError):
            bus.subscribe_self_observation(
                plugin=None,  # type: ignore[arg-type]
                category=SINKS_END,
                on_event=lambda p, r: None,
            )


# ── Observer 派生 ───────────────────────────────────────────────────────


class TestObserverEmission:
    def test_consumers_end_emitted(
        self,
        bus: EventBus[EventPayload],
        authorized_plugin: type,
        subscriber_plugin: type,
        payload: TeamDelegationCacheHit,
    ) -> None:
        """有 CONTAINED subscriber → 派生 consumers.end。"""
        _install_observer(bus)
        captured = _capture(bus)
        bus.subscribe(
            plugin=subscriber_plugin,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=lambda p, r: None,
            failure=FailureSemantics.CONTAINED,
        )
        ref = bus.publish(payload, producer=authorized_plugin)
        consumers = [p for p, _ in captured if p.category == CONSUMERS_END]
        assert len(consumers) == 1
        assert consumers[0].consumer_count == 1
        assert consumers[0].contained_failures == ()
        # sinks 阶段无 FAIL_FAST consumer → 不派生 sinks.end
        assert not [p for p, _ in captured if p.category == SINKS_END]
        assert ref.trace_id != ""

    def test_sinks_end_emitted(
        self,
        bus: EventBus[EventPayload],
        authorized_plugin: type,
        subscriber_plugin: type,
        payload: TeamDelegationCacheHit,
    ) -> None:
        """有 FAIL_FAST sink → 派生 sinks.end。"""
        _install_observer(bus)
        captured = _capture(bus)
        bus.subscribe(
            plugin=subscriber_plugin,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=lambda p, r: None,
            failure=FailureSemantics.FAIL_FAST,
        )
        bus.publish(payload, producer=authorized_plugin)
        sinks = [p for p, _ in captured if p.category == SINKS_END]
        assert len(sinks) == 1
        assert sinks[0].consumer_count == 1

    def test_both_stages_emitted(
        self,
        bus: EventBus[EventPayload],
        authorized_plugin: type,
        subscriber_plugin: type,
        payload: TeamDelegationCacheHit,
    ) -> None:
        _install_observer(bus)
        captured = _capture(bus)
        bus.subscribe(
            plugin=subscriber_plugin,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=lambda p, r: None,
            failure=FailureSemantics.FAIL_FAST,
        )
        bus.subscribe(
            plugin=subscriber_plugin,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=lambda p, r: None,
            failure=FailureSemantics.CONTAINED,
        )
        bus.publish(payload, producer=authorized_plugin)
        cats = [p.category for p, _ in captured]
        assert SINKS_END in cats
        assert CONSUMERS_END in cats

    def test_contained_failure_recorded(
        self,
        bus: EventBus[EventPayload],
        authorized_plugin: type,
        subscriber_plugin: type,
        payload: TeamDelegationCacheHit,
    ) -> None:
        """CONTAINED consumer 抛错 → 吞错且记入 contained_failures。"""

        def boom(_p, _r):
            raise RuntimeError("contained")

        _install_observer(bus)
        captured = _capture(bus)
        bus.subscribe(
            plugin=subscriber_plugin,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=boom,
            failure=FailureSemantics.CONTAINED,
        )
        bus.publish(payload, producer=authorized_plugin)
        consumers = [p for p, _ in captured if p.category == CONSUMERS_END]
        assert len(consumers) == 1
        assert consumers[0].contained_failures == ("RuntimeError",)


# ── trace 继承 ──────────────────────────────────────────────────────────


class TestTraceContinuity:
    def test_self_observation_inherits_trace(
        self,
        bus: EventBus[EventPayload],
        authorized_plugin: type,
        subscriber_plugin: type,
        payload: TeamDelegationCacheHit,
    ) -> None:
        _install_observer(bus)
        captured = _capture(bus)
        bus.subscribe(
            plugin=subscriber_plugin,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=lambda p, r: None,
        )
        tok = set_trace_id("trc_parent")
        try:
            ref = bus.publish(payload, producer=authorized_plugin)
        finally:
            reset_trace_id(tok)
        assert ref.trace_id == "trc_parent"
        for _p, r in captured:
            assert r.trace_id == "trc_parent"


# ── 防递归守卫 ──────────────────────────────────────────────────────────


class TestAntiRecursion:
    def test_no_self_observation_of_self_observation(
        self,
        bus: EventBus[EventPayload],
        authorized_plugin: type,
        subscriber_plugin: type,
        payload: TeamDelegationCacheHit,
    ) -> None:
        """自观察事件不再触发 MechanismDispatchObserver(结构守卫)。

        若存在递归,每次 publish 会产生 >1 个同阶段自观察事件;
        断言恰好 1 个 consumers.end,且无二代事件。
        """
        _install_observer(bus)
        captured = _capture(bus)
        bus.subscribe(
            plugin=subscriber_plugin,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=lambda p, r: None,
        )
        bus.publish(payload, producer=authorized_plugin)
        assert len(captured) == 1
        assert captured[0][0].category == CONSUMERS_END

    def test_self_observation_not_fanned_out_to_subscribers(
        self,
        bus: EventBus[EventPayload],
        authorized_plugin: type,
        subscriber_plugin: type,
        payload: TeamDelegationCacheHit,
    ) -> None:
        """自观察事件不进业务 _subscribers(I-FW-BUS-4)。"""
        business_calls: list[str] = []
        _install_observer(bus)
        _capture(bus)
        bus.subscribe(
            plugin=subscriber_plugin,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=lambda p, r: business_calls.append(p.category.value),
        )
        bus.publish(payload, producer=authorized_plugin)
        # 业务 callback 只见到业务事件,见不到 event.bus.dispatch.*
        assert business_calls == ["team.delegation.cache_hit"]
