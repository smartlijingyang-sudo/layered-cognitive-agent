"""ADR-0180 试点：DelegationCachePlugin (publisher) 测试 / ADR-0183 PR-7。"""

from __future__ import annotations

from dataclasses import replace

from lca.contracts.atoms.ids import new_id
from lca.contracts.event import Category
from lca.contracts.models.core.decision import DelegationSpec, Observation
from lca.contracts.models.core.state import AgentState, Budget
from lca.plugins.events.publishers.delegation_cache.plugin import (
    PUBLISHER_PLUGIN_ID,
    DelegationCachePlugin,
)
from lca_kernel.events import TeamDelegationCacheHit
from lca_kernel.events.bus import EventBus, EventRef


def _state_with_hit_result(
    state: AgentState, role: str = "analyst", subtask: str = "汇总"
) -> AgentState:
    from datetime import datetime, timezone

    from lca.contracts.models.team.delegation import DelegationResult
    from lca.contracts.models.team.team_awareness import TeamAwareness

    awareness = TeamAwareness(
        results=(
            DelegationResult(
                result_id=new_id("res"),
                target_role=role,
                subtask=subtask,
                output="done",
                success=True,
                error=None,
                task_id=new_id("task"),
                step=0,
                returned_at=datetime.now(tz=timezone.utc),
            ),
        )
    )
    return replace(state, team_awareness=awareness, step=3)


def _state() -> AgentState:
    return AgentState(trace_id="t-1", task="汇总", budget=Budget())


def test_publisher_plugin_id_matches_yaml() -> None:
    """plugin id 是 stable 字符串（用于日志 / ctx.provide key）；plugin class 用于鉴权。"""
    assert PUBLISHER_PLUGIN_ID == "delegation_cache"


def test_delegation_cache_plugin_emits_event_via_bus() -> None:
    """业务方 plugin 类直接 publish → EventBus 按 yaml 鉴权通过 → 事件被路由。"""
    from lca_kernel.events.test_catalog import build_test_bus
    bus = build_test_bus()
    EventBus.set_default(bus)

    received: list[EventRef] = []
    from lca.plugins.events.subscribers.console_projector.subscriber import (
        ConsoleProjectorSubscriber,
    )

    bus.subscribe(
        plugin=ConsoleProjectorSubscriber,
        category=Category.TEAM_DELEGATION_CACHE_HIT,
        on_event=lambda p, r: received.append(r),
    )

    try:
        state = _state_with_hit_result(_state())
        spec = DelegationSpec(target_role="analyst", subtask="汇总")
        observation = DelegationCachePlugin().cached_observation(spec, state)
    finally:
        EventBus.reset_singleton()

    assert isinstance(observation, Observation)
    assert observation.success is True
    assert len(received) == 1
    assert received[0].category == "team.delegation.cache_hit"


def test_cached_observation_no_hit_returns_none() -> None:
    """无命中：不发事件，返回 None。"""
    state = _state()
    spec = DelegationSpec(target_role="analyst", subtask="汇总")
    assert DelegationCachePlugin().cached_observation(spec, state) is None


def test_compatibility_shell_delegates_to_plugin() -> None:
    """cognition 模块的 cached_delegation_observation 兼容壳 → DelegationCachePlugin。"""
    from lca.cognition.body.delegation_cache import cached_delegation_observation
    from lca_kernel.events.test_catalog import build_test_bus
    bus = build_test_bus()
    EventBus.set_default(bus)

    received: list = []
    from lca.plugins.events.subscribers.console_projector.subscriber import (
        ConsoleProjectorSubscriber,
    )

    bus.subscribe(
        plugin=ConsoleProjectorSubscriber,
        category=Category.TEAM_DELEGATION_CACHE_HIT,
        on_event=lambda p, r: received.append(p),
    )

    try:
        state = _state_with_hit_result(_state())
        spec = DelegationSpec(target_role="analyst", subtask="汇总")
        observation = cached_delegation_observation(spec, state)
    finally:
        EventBus.reset_singleton()

    assert isinstance(observation, Observation)
    assert len(received) == 1


def test_unauthorized_plugin_class_cannot_publish() -> None:
    """未在 yaml publishers 白名单的 plugin class → UnauthorizedPublishError。"""

    class _RoguePlugin:
        pass

    from lca_kernel.events.test_catalog import build_test_bus
    bus = build_test_bus()
    EventBus.set_default(bus)
    try:
        with __import__("pytest").raises(
            __import__(
                "lca_kernel.events.errors", fromlist=["UnauthorizedPublishError"]
            ).UnauthorizedPublishError
        ):
            bus.publish(
                TeamDelegationCacheHit(callee_role="x", subtask="y", step=0),
                producer=_RoguePlugin,
            )
    finally:
        EventBus.reset_singleton()
