"""PR-12 trace_id contextvars 注入 + 解析链单元测试（迁移 EventBus-only / ADR-0183 PR-7）。

覆盖:
- set_trace_id / reset_trace_id / current_trace_id 三件套
- publish 解析链:显式参数 > payload.trace_id > contextvars > new_id("trc")
- TraceContextHook 透传(解析由 EventBus 单点承担)
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.ids import new_id
from lca.contracts.event import EventPayload
from lca_kernel.events import TeamDelegationCacheHit
from lca_kernel.events.bus import (
    EventBus,
    current_trace_id,
    reset_trace_id,
    set_trace_id,
)
from lca_kernel.events.hooks import PublishContext, TraceContextHook
from lca_kernel.events.mechanism import _DEFAULT_CONFIG_DIR
from lca_kernel.events.registry import EventRegistry


def _make_bus() -> EventBus[EventPayload]:
    registry = EventRegistry.load(_DEFAULT_CONFIG_DIR)
    return EventBus(registry)


@pytest.fixture
def bus() -> EventBus[EventPayload]:
    return _make_bus()


@pytest.fixture(autouse=True)
def _reset_ambient_trace():
    """每个测试独立:收尾强制清 ambient trace,防跨用例串。"""
    yield
    from lca_kernel.events import bus as bus_module

    bus_module._current_trace_id.set(None)


@pytest.fixture
def authorized_plugin() -> type:
    from lca.plugins.events.publishers.delegation_cache.plugin import (
        DelegationCachePlugin,
    )

    return DelegationCachePlugin


@pytest.fixture
def payload() -> TeamDelegationCacheHit:
    return TeamDelegationCacheHit(callee_role="a", subtask="b", step=1)


# ── contextvars 三件套 ──────────────────────────────────────────────────


class TestTraceContextVar:
    def test_set_and_current(self) -> None:
        tok = set_trace_id("trc_abc")
        try:
            assert current_trace_id() == "trc_abc"
        finally:
            reset_trace_id(tok)

    def test_reset_restores_default(self) -> None:
        assert current_trace_id() is None
        tok = set_trace_id("trc_tmp")
        reset_trace_id(tok)
        assert current_trace_id() is None

    def test_nested_set_reset(self) -> None:
        outer = set_trace_id("trc_outer")
        inner = set_trace_id("trc_inner")
        assert current_trace_id() == "trc_inner"
        reset_trace_id(inner)
        assert current_trace_id() == "trc_outer"
        reset_trace_id(outer)
        assert current_trace_id() is None


# ── publish 解析链 ──────────────────────────────────────────────────────


class TestPublishTraceResolution:
    def test_explicit_param_wins(
        self, bus: EventBus[EventPayload], authorized_plugin: type
    ) -> None:
        """显式 trace_id 参数优先级最高(即使 ambient 已设)。"""
        ambient = set_trace_id("trc_ambient")
        try:
            p = TeamDelegationCacheHit(callee_role="a", subtask="b", step=1)
            ref = bus.publish(p, producer=authorized_plugin, trace_id="trc_explicit")
            assert ref.trace_id == "trc_explicit"
        finally:
            reset_trace_id(ambient)

    def test_contextvar_used_when_no_explicit(
        self, bus: EventBus[EventPayload], authorized_plugin: type
    ) -> None:
        ambient = set_trace_id("trc_ambient")
        try:
            p = TeamDelegationCacheHit(callee_role="a", subtask="b", step=1)
            ref = bus.publish(p, producer=authorized_plugin)
            assert ref.trace_id == "trc_ambient"
        finally:
            reset_trace_id(ambient)

    def test_generated_when_no_source(
        self, bus: EventBus[EventPayload], authorized_plugin: type
    ) -> None:
        p = TeamDelegationCacheHit(callee_role="a", subtask="b", step=1)
        ref = bus.publish(p, producer=authorized_plugin)
        assert ref.trace_id.startswith("trc")
        assert ref.trace_id != ""

    def test_payload_trace_id_beats_contextvar(
        self, bus: EventBus[EventPayload], authorized_plugin: type
    ) -> None:
        """payload.trace_id 属性优先于 ambient contextvars。"""

        class TracedPayload(TeamDelegationCacheHit):
            trace_id: str = "trc_from_payload"

        ambient = set_trace_id("trc_ambient")
        try:
            p = TracedPayload(callee_role="a", subtask="b", step=1)
            ref = bus.publish(p, producer=authorized_plugin)
            assert ref.trace_id == "trc_from_payload"
        finally:
            reset_trace_id(ambient)


# ── TraceContextHook 透传 ───────────────────────────────────────────────


class TestTraceContextHook:
    def test_before_publish_passthrough(
        self, bus: EventBus[EventPayload], authorized_plugin: type
    ) -> None:
        """TraceContextHook 不改 payload(解析在 EventBus._resolve_trace_id)。"""
        hook = TraceContextHook()
        p = TeamDelegationCacheHit(callee_role="a", subtask="b", step=1)
        ctx = PublishContext(bus=bus, producer=authorized_plugin, ts=0.0)
        result = hook.before_publish(p, authorized_plugin, ctx)
        assert result is p


# ── new_id 格式一致性 ──────────────────────────────────────────────────


def test_new_id_trace_prefix() -> None:
    assert new_id("trc").startswith("trc")
