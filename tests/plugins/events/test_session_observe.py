"""ADR-0186 PR-3f 回归锁：Session.observe 目录 + sink/subscriber 迁移。

守护:

1. :func:`register_as_session_observer` 在 Session 未装载时入目录并返回 ``False``;
2. Session 装载后经 ``observe(plugin, callback)`` 完成注册并返回 ``True``;
3. :func:`set_session` 把目录整表挂到新 Session（run-bind 路径）;
4. 全部 sink/subscriber setup 只走目录登记 —— 不触碰
   ``EventBus.subscribe`` / ``mount_sink``（``spine_file_sink`` /
   ``spine_file_sink`` /
   ``spine_step_tree_accumulator``）。
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from lca.contracts.event import EventPayload
from lca.plugins.events import _session_observe
from lca.plugins.events._session_observe import (
    clear_observer_catalog,
    observer_catalog,
    register_as_session_observer,
    set_session,
)
from lca.plugins.events.sinks.spine_file_sink.manifest import (
    SINK_PLUGIN_CLASS,
)
from lca.plugins.events.sinks.spine_file_sink.manifest import (
    setup as sink_setup,
)
from lca_kernel.events import EventRef


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
    clear_observer_catalog()
    yield
    set_session(None)
    clear_observer_catalog()


# ── helper 契约 ────────────────────────────────────────────────────────


def test_register_returns_false_without_session_but_catalogues() -> None:
    """Session 未装载 → False，callback 仍入目录等 set_session。"""

    def callback(payload: EventPayload, ref: EventRef) -> None:
        del payload, ref

    assert register_as_session_observer(_RecordingSession, callback) is False
    assert observer_catalog() == {_RecordingSession: callback}


def test_register_routes_through_installed_session() -> None:
    """Session 装载 → observe(plugin, callback) 收到同一实参,返回 True。"""
    session = _RecordingSession()
    set_session(session)

    def callback(payload: EventPayload, ref: EventRef) -> None:
        del payload, ref

    assert register_as_session_observer(_RecordingSession, callback) is True
    assert session.observed == [(_RecordingSession, callback)]


def test_set_session_attaches_catalogued_observers() -> None:
    """Boot 先登记、run bind 再 set_session → 目录整表挂上。"""

    def callback(payload: EventPayload, ref: EventRef) -> None:
        del payload, ref

    assert register_as_session_observer(_RecordingSession, callback) is False
    session = _RecordingSession()
    set_session(session)
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
    ctx = _StubPluginContext()

    asyncio.run(sink_setup.setup(ctx, sink_setup.Config()))

    sink = ctx.provided["event.sink.spine_file"]
    assert session.observed == [(SINK_PLUGIN_CLASS, sink)]


def test_spine_file_sink_setup_catalogues_without_session() -> None:
    """Session 缺席:只 provide + 入目录，不 mount_sink。"""
    ctx = _StubPluginContext()

    asyncio.run(sink_setup.setup(ctx, sink_setup.Config()))

    sink = ctx.provided["event.sink.spine_file"]
    assert observer_catalog()[SINK_PLUGIN_CLASS] is sink
    session = _RecordingSession()
    set_session(session)
    assert session.observed == [(SINK_PLUGIN_CLASS, sink)]


# ── ConsoleProjector 样本 ──────────────────────────────────────────────
