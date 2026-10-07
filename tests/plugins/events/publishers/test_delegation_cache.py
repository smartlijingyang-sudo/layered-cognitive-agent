"""ADR-0180 试点：DelegationCachePlugin (publisher) 测试 / ADR-0183 PR-7。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.event import Category
from lca.contracts.models.core.execution.decision import DelegationSpec, Observation
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.loop.fact_gateway import DefaultFactGateway
from lca.plugins.events.publishers.delegation_cache.plugin import (
    PUBLISHER_PLUGIN_ID,
    DelegationCachePlugin,
)
from lca_kernel.events import TeamDelegationCacheHit
from lca_kernel.events.bus.bus import EnvelopeBus, EventRef


def _state_with_hit_result(
    state: AgentState, role: str = "analyst", subtask: str = "汇总"
) -> AgentState:
    from datetime import datetime

    from lca.contracts.models.team.delegation.delegation import DelegationResult
    from lca.contracts.models.team.team.awareness import TeamAwareness

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
                returned_at=datetime.now(tz=UTC),
            ),
        )
    )
    return replace(state, team_awareness=awareness, step=3)


def _state() -> AgentState:
    return AgentState(trace_id="t-1", task="汇总", budget=Budget())


def test_publisher_plugin_id_matches_yaml() -> None:
    """plugin id 是 stable 字符串（用于日志 / ctx.provide key）；plugin class 用于鉴权。"""
    assert PUBLISHER_PLUGIN_ID == "delegation_cache"


def test_manifest_provides_match_setup_keys() -> None:
    """provides 必须 ⊆ setup 实际 provide 的键（e2e bind_plan 回归）。

    曾声明未 provide 的 ``delegation.cache_observation``，CompiledRunPlan
    把它编进 ProviderBinding 后 spawn 全挂。
    """
    from lca.harness.plugin.declaration import definition_from_plugin
    from lca.plugins.events.publishers.delegation_cache import plugin as mod

    definition = definition_from_plugin(mod.setup, module=__name__)
    assert definition.provided_capability_keys == (PUBLISHER_PLUGIN_ID,)


def test_delegation_cache_plugin_emits_via_session() -> None:
    """命中缓存 → Session.append(TeamDelegationCacheHit) + Observation。"""
    from typing import Any

    from lca.plugins.events.publishers._session_publish import (
        reset_publish_session,
        set_publish_session,
    )
    from lca_kernel.events.test.catalog import build_test_bus

    bus = build_test_bus()
    EnvelopeBus.set_default(bus)
    captured: dict[str, Any] = {}

    class FakeSession:
        def append(self, payload: Any, *, producer: Any) -> EventRef:
            captured["payload"] = payload
            captured["producer"] = producer
            return EventRef(
                event_id="test-delegation-cache:1",
                category="team.delegation.cache_hit",
                trace_id="test-delegation-cache",
                ts=0.0,
                persisted=False,
                subscriber_count=0,
            )

    token = set_publish_session(FakeSession())
    try:
        state = _state_with_hit_result(_state())
        spec = DelegationSpec(target_role="analyst", subtask="汇总")
        observation = DelegationCachePlugin().cached_observation(spec, state)
    finally:
        reset_publish_session(token)
        EnvelopeBus.reset_singleton()

    assert isinstance(observation, Observation)
    assert observation.success is True
    payload = captured["payload"]
    # commit_delegation_cache_hit publishes a spine fact (ADR-0193 taxonomy);
    # the session now receives a SpineEventPayload envelope, not the DTO.
    assert payload.category == Category.SPINE_TEAM_DELEGATION_CACHE_HIT
    # Fact-gateway seam: DefaultFactGateway is the session producer
    # for spine facts (see publish_ep observer-path comment).
    assert captured["producer"] is DefaultFactGateway
    assert payload.payload["callee_role"] == "analyst"


def test_cached_observation_no_hit_returns_none() -> None:
    """无命中：不发事件，返回 None。"""
    state = _state()
    spec = DelegationSpec(target_role="analyst", subtask="汇总")
    assert DelegationCachePlugin().cached_observation(spec, state) is None


def test_cache_module_delegates_to_plugin() -> None:
    """infrastructure 缓存模块 → DelegationCachePlugin → Session.append。"""
    from typing import Any

    from lca.infrastructure.delegation.cache import cached_delegation_observation
    from lca.plugins.events.publishers._session_publish import (
        reset_publish_session,
        set_publish_session,
    )
    from lca_kernel.events.test.catalog import build_test_bus

    bus = build_test_bus()
    EnvelopeBus.set_default(bus)
    captured: list[Any] = []

    class FakeSession:
        def append(self, payload: Any, *, producer: Any) -> EventRef:
            del producer
            captured.append(payload)
            return EventRef(
                event_id="test-delegation-cache:2",
                category="team.delegation.cache_hit",
                trace_id="test-delegation-cache",
                ts=0.0,
                persisted=False,
                subscriber_count=0,
            )

    token = set_publish_session(FakeSession())
    try:
        state = _state_with_hit_result(_state())
        spec = DelegationSpec(target_role="analyst", subtask="汇总")
        observation = cached_delegation_observation(spec, state)
    finally:
        reset_publish_session(token)
        EnvelopeBus.reset_singleton()

    assert isinstance(observation, Observation)
    assert len(captured) == 1
    assert captured[0].category == Category.SPINE_TEAM_DELEGATION_CACHE_HIT
    assert captured[0].payload["callee_role"] == "analyst"


def test_unauthorized_plugin_class_cannot_publish() -> None:
    """未在 yaml publishers 白名单的 plugin class → UnauthorizedPublishError。"""

    class _RoguePlugin:
        pass

    from lca_kernel.events.test.catalog import build_test_bus

    bus = build_test_bus()
    EnvelopeBus.set_default(bus)
    try:
        with __import__("pytest").raises(
            __import__(
                "lca_kernel.events.errors.errors", fromlist=["UnauthorizedPublishError"]
            ).UnauthorizedPublishError
        ):
            bus.publish(
                TeamDelegationCacheHit(callee_role="x", subtask="y", step=0),
                producer=_RoguePlugin,
            )
    finally:
        EnvelopeBus.reset_singleton()
