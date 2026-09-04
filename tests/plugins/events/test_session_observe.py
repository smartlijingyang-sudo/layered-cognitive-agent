"""PR-3f-sample 回归锁：Session.observe 注册接缝 + 全部 sink/subscriber 迁移。

守护六件事:

1. :func:`register_as_session_observer` 在 Session 未装载时返回 ``False``
   (调用方走 bus fallback);
2. Session 装载后经 ``observe(plugin, callback)`` 完成注册;
3. 所有 sink/subscriber plugin setup 优先 Session.observe —— Session 在场时
   不触碰 EventBus:
   - sinks: ``spine_file_sink`` / ``spine_chain_sink`` / ``journal``;
   - subscribers: ``console_projector`` / ``spine_step_tree_accumulator``;
4. Session 缺席时回退原 wire:sinks 走 ``mount_sink`` 落盘,subscribers 走
   ``bus.subscribe`` 逐条接线。
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from lca.contracts.event import EventPayload, TeamDelegationCacheHit
from lca.plugins.events import _session_observe
from lca.plugins.events._session_observe import (
    register_as_session_observer,
    set_session,
)
from lca.plugins.events.publishers.delegation_cache.plugin import DelegationCachePlugin
from lca.plugins.events.publishers.spine_reflector_cognition.plugin import ReflectorClass
from lca.plugins.events.sinks.journal.manifest import (
    SINK_PLUGIN_CLASS as JOURNAL_PLUGIN_CLASS,
)
from lca.plugins.events.sinks.journal.manifest import (
    setup as journal_setup,
)
from lca.plugins.events.sinks.spine_chain_sink.sink import (
    SpineChainSink,
)
from lca.plugins.events.sinks.spine_chain_sink.sink import setup as chain_setup
from lca.plugins.events.sinks.spine_file_sink.manifest import (
    SINK_PLUGIN_CLASS,
)
from lca.plugins.events.sinks.spine_file_sink.manifest import (
    setup as sink_setup,
)
from lca.plugins.events.subscribers.console_projector.manifest import (
    SUBSCRIBER_PLUGIN_CLASS,
)
from lca.plugins.events.subscribers.console_projector.manifest import (
    setup as projector_setup,
)
from lca.plugins.events.subscribers.spine_step_tree_accumulator.subscriber import (
    SpineStepTreeAccumulator,
)
from lca.plugins.events.subscribers.spine_step_tree_accumulator.subscriber import (
    setup as step_tree_setup,
)
from lca_kernel.events import EventRef
from lca_kernel.events.payloads import SpineEventPayload
from lca_kernel.events.test_catalog import build_test_bus


class _RecordingSession:
    """Session 观察目标 stub:记录 observe(plugin, callback) 调用。"""

    def __init__(self) -> None:
        self.observed: list[tuple[type, Any]] = []

    def observe(self, plugin: type, callback: Any) -> None:
        self.observed.append((plugin, callback))


class _StubPluginContext:
    """最小 PluginContext:provide 记录 + soft_get 按字典命中。"""

    def __init__(self, capabilities: dict[str, Any] | None = None) -> None:
        self._capabilities = capabilities or {}
        self.provided: dict[str, Any] = {}

    def provide(self, key: str, value: object, **kwargs: object) -> None:
        del kwargs
        self.provided[key] = value

    def soft_get(self, key: str) -> Any | None:
        return self._capabilities.get(key)


@pytest.fixture(autouse=True)
def _clean_session() -> Iterator[None]:
    set_session(None)
    yield
    set_session(None)


# ── helper 契约 ────────────────────────────────────────────────────────


def test_register_returns_false_without_session() -> None:
    """Session 未装载 → False,调用方必须走 bus fallback。"""

    def callback(payload: EventPayload, ref: EventRef) -> None:
        del payload, ref

    assert register_as_session_observer(_RecordingSession, callback) is False


def test_register_routes_through_installed_session() -> None:
    """Session 装载 → observe(plugin, callback) 收到同一实参,返回 True。"""
    session = _RecordingSession()
    set_session(session)

    def callback(payload: EventPayload, ref: EventRef) -> None:
        del payload, ref

    assert register_as_session_observer(_RecordingSession, callback) is True
    assert session.observed == [(_RecordingSession, callback)]


def test_set_session_rejects_target_without_observe() -> None:
    """无 observe 的对象装载即抛 —— 禁止静默降级成无观察态。"""
    with pytest.raises(TypeError, match="observe"):
        set_session(object())  # type: ignore[arg-type]


def test_current_session_tracks_install_and_clear() -> None:
    session = _RecordingSession()
    set_session(session)
    assert _session_observe.current_session() is session
    set_session(None)
    assert _session_observe.current_session() is None


# ── SpineFileSink 样本 ─────────────────────────────────────────────────


def test_spine_file_sink_setup_prefers_session_observe() -> None:
    """Session 在场:注册走 observe,不依赖 event.bus 能力。"""
    session = _RecordingSession()
    set_session(session)
    ctx = _StubPluginContext()  # 无 event.bus —— Session 路径不触碰 bus

    asyncio.run(sink_setup.setup(ctx, sink_setup.Config()))

    sink = ctx.provided["event.sink.spine_file"]
    assert session.observed == [(SINK_PLUGIN_CLASS, sink)]


def test_spine_file_sink_setup_falls_back_to_mount_sink(tmp_path, monkeypatch) -> None:
    """Session 缺席:回退 mount_sink,publish 经 _dispatch_sinks 落盘。"""
    monkeypatch.chdir(tmp_path)
    bus = build_test_bus()
    ctx = _StubPluginContext({"event.bus": bus})

    asyncio.run(sink_setup.setup(ctx, sink_setup.Config()))

    sink = ctx.provided["event.sink.spine_file"]
    bus.publish(
        SpineEventPayload(
            execution_point="brain.perceive.start",
            channel="fact",
            payload={"state_id": "s1"},
        ),
        producer=ReflectorClass,
    )
    sink.flush()
    try:
        target = tmp_path / "default-run.spine.jsonl"
        assert target.is_file()
        assert len(target.read_text(encoding="utf-8").splitlines()) == 1
    finally:
        sink.close()


# ── ConsoleProjector 样本 ──────────────────────────────────────────────


def test_console_projector_setup_prefers_session_observe() -> None:
    """Session 在场:on_event 经 observe 注册,不依赖 event.bus 能力。"""
    session = _RecordingSession()
    set_session(session)
    ctx = _StubPluginContext()

    asyncio.run(projector_setup.setup(ctx, projector_setup.Config()))

    subscriber = ctx.provided["event.subscriber.console_projector"]
    plugin, callback = session.observed[0]
    assert plugin is SUBSCRIBER_PLUGIN_CLASS
    assert callback == subscriber.on_event


def test_console_projector_setup_falls_back_to_bus_subscribe(capsys) -> None:
    """Session 缺席:回退逐条 subscribe,publish 派发到 subscriber 渲染。"""
    bus = build_test_bus()
    ctx = _StubPluginContext({"event.bus": bus})

    asyncio.run(projector_setup.setup(ctx, projector_setup.Config()))

    ref = bus.publish(
        TeamDelegationCacheHit(callee_role="worker", subtask="t", step=1),
        producer=DelegationCachePlugin,
    )
    assert ref.subscriber_count == 1
    captured = capsys.readouterr()
    assert "worker" in captured.out


# ── JournalSink 样本 ──────────────────────────────────────────────────


def test_journal_sink_setup_prefers_session_observe() -> None:
    """Session 在场:on_event 经 observe 注册,不依赖 event.bus 能力。"""
    session = _RecordingSession()
    set_session(session)
    ctx = _StubPluginContext()

    asyncio.run(journal_setup.setup(ctx, journal_setup.Config()))

    sink = ctx.provided["event.sink.journal"]
    plugin, callback = session.observed[0]
    assert plugin is JOURNAL_PLUGIN_CLASS
    assert callback == sink.on_event


def test_journal_sink_setup_falls_back_to_bus_subscribe() -> None:
    """Session 缺席:回退逐条 subscribe,publish 派发到 journal 缓存。"""
    bus = build_test_bus()
    ctx = _StubPluginContext({"event.bus": bus})

    asyncio.run(journal_setup.setup(ctx, journal_setup.Config()))

    ref = bus.publish(
        TeamDelegationCacheHit(callee_role="writer", subtask="t", step=0),
        producer=DelegationCachePlugin,
    )
    assert ref.subscriber_count == 1
    sink = ctx.provided["event.sink.journal"]
    assert len(sink.records) == 1
    assert sink.records[0].category == "team.delegation.cache_hit"


# ── SpineChainSink 样本 ───────────────────────────────────────────────


def test_spine_chain_sink_setup_prefers_session_observe(tmp_path) -> None:
    """Session 在场:sink 注册走 observe,不依赖 event.bus 能力。"""
    session = _RecordingSession()
    set_session(session)
    ctx = _StubPluginContext()

    asyncio.run(chain_setup.setup(ctx, chain_setup.Config()))

    sink = ctx.provided["event.bus.chain_sink"]
    plugin, callback = session.observed[0]
    assert plugin is SpineChainSink
    assert callback is sink


def test_spine_chain_sink_setup_falls_back_to_marker() -> None:
    """Session 缺席:回退原 wire —— 验证 bus + 提供 marker,不自动 subscribe。

    鉴权受 ``spine.`` 前缀白名单限制；yaml 物化后 plugin 上线时由装配路径
    按 category 逐条订阅,setup 不重做（避免 PR-6 鉴权三方冲突）。
    """
    bus = build_test_bus()
    ctx = _StubPluginContext({"event.bus": bus})

    asyncio.run(chain_setup.setup(ctx, chain_setup.Config()))

    sink = ctx.provided["event.bus.chain_sink"]
    assert isinstance(sink, SpineChainSink)


# ── SpineStepTreeAccumulator 样本 ─────────────────────────────────────


def test_spine_step_tree_accumulator_setup_prefers_session_observe() -> None:
    """Session 在场:subscriber 注册走 observe,不依赖 event.bus 能力。"""
    SpineStepTreeAccumulator.reset()
    session = _RecordingSession()
    set_session(session)
    ctx = _StubPluginContext()

    asyncio.run(step_tree_setup.setup(ctx, step_tree_setup.Config()))

    subscriber = ctx.provided["event.bus.step_tree_accumulator"]
    plugin, callback = session.observed[0]
    assert plugin is SpineStepTreeAccumulator
    assert callback is subscriber


def test_spine_step_tree_accumulator_setup_falls_back_to_marker() -> None:
    """Session 缺席:回退原 wire —— 仅注册 marker 并提供 capability。

    鉴权受 ``spine.cognition.brain.perceive.*`` 子树白名单限制；setup
    不重做 category subscribe（避免 PR-6 鉴权三方冲突），下游装配路径
    按 yaml 物化的 category 逐条订阅。
    """
    SpineStepTreeAccumulator.reset()
    ctx = _StubPluginContext({"event.bus": build_test_bus()})

    asyncio.run(step_tree_setup.setup(ctx, step_tree_setup.Config()))

    subscriber = ctx.provided["event.bus.step_tree_accumulator"]
    assert isinstance(subscriber, SpineStepTreeAccumulator)
    assert subscriber._state == []
