"""Session runtime plugin 测试（PR-3c 骨架）。

覆盖 4 类契约：

- create + append + snapshot（DSH ``Session.append`` 语义链）
- reentry 拒绝（:class:`SessionReentryError`，日志不变）
- observer 失败 contained（单点失败不打断提交链）
- ``request_header`` 增量 fold（与 ``foldRequestHeader`` 全量形态一致）

外加 SessionStore 生命周期与 plugin 装配 / manifest 元数据。
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.plugins.session.runtime.session import Session
from lca.plugins.session.runtime.store import SessionStore
from lca_kernel.events.fold import EpochHeader, foldRequestHeader, headerEquals
from lca_kernel.events.session import (
    SESSION_FORMAT_VERSION,
    SessionEvent,
    SessionProtocol,
    SessionReentryError,
)

REQUEST_HEADER = "spine.llm.request.header"


def _header_payload(*, system: str = "sys-v1", model: str = "m1") -> dict[str, Any]:
    """fold 可识别的 header payload（config / system / tools 原文）。"""
    return {
        "config": {"provider": "p", "model": model},
        "system": system,
        "tools": [{"type": "function", "function": {"name": "t1"}}],
    }


# ── create + append + snapshot ────────────────────────────────────────


def test_store_create_append_snapshot() -> None:
    store = SessionStore()
    session = store.create()
    assert session.id == "session-1"
    assert store.get(session.id) is session
    assert isinstance(session, SessionProtocol)

    event = session.append("spine.turn.started", {"turn": 1})
    assert isinstance(event, SessionEvent)
    assert event.type == "spine.turn.started"
    assert event.seq == 0
    assert event.time > 0
    assert event.data == {"turn": 1}
    assert session.seq == 1

    snapshot = session.snapshot_events()
    assert snapshot == (event,)
    assert session.event_at(0) is event
    assert session.event_at(1) is None
    assert session.event_at(-1) is None


def test_append_snapshots_data_detached_from_caller() -> None:
    session = SessionStore().create()
    data: dict[str, Any] = {"turn": 1, "nested": {"k": "v"}}
    event = session.append("spine.turn.started", data)

    data["turn"] = 99
    data["nested"]["k"] = "mutated"

    assert event.data == {"turn": 1, "nested": {"k": "v"}}
    assert session.event_at(0) is event


def test_append_rejects_non_json_data_and_keeps_log() -> None:
    session = SessionStore().create()

    with pytest.raises(TypeError):
        session.append("x", {"obj": object()})
    with pytest.raises(TypeError):
        session.append("x", {"nan": float("nan")})
    with pytest.raises(TypeError):
        session.append("x", [1, 2])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="非空字符串"):
        session.append("", {"k": 1})

    assert session.seq == 0
    assert session.snapshot_events() == ()


def test_snapshot_range_and_bounds() -> None:
    session = SessionStore().create()
    events = [session.append("t", {"i": i}) for i in range(4)]

    full_first = session.snapshot_events()
    full_second = session.snapshot_events()
    assert full_first == tuple(events)
    assert full_first is full_second  # 全量快照缓存：下次 append 前复用

    assert session.snapshot_events(1, 3) == (events[1], events[2])
    assert session.snapshot_events(2) == (events[2], events[3])

    session.append("t", {"i": 4})
    assert session.snapshot_events() is not full_first  # append 失效缓存

    with pytest.raises(ValueError, match="越界"):
        session.snapshot_events(-1)
    with pytest.raises(ValueError, match="越界"):
        session.snapshot_events(0, 99)
    with pytest.raises(ValueError, match="越界"):
        session.snapshot_events(3, 1)


def test_header_synthesized_with_format_version() -> None:
    session = SessionStore().create("s-x")
    assert session.header.id == "s-x"
    assert session.header.version == SESSION_FORMAT_VERSION
    assert session.header.is_seeded is False
    assert session.header.created_at > 0

    with pytest.raises(ValueError, match="不一致"):
        Session("a", header=session.header)  # header.id != session_id


# ── reentry 拒绝 ─────────────────────────────────────────────────────


def test_reentry_raises_session_reentry_error() -> None:
    session = SessionStore().create()
    nested_errors: list[Exception] = []

    def reentrant_observer(target: SessionProtocol, event: SessionEvent) -> None:
        try:
            target.append("nested", {"from": event.seq})
        except SessionReentryError as exc:
            nested_errors.append(exc)

    session.observe(reentrant_observer)
    outer = session.append("outer", {"k": 1})

    assert outer.seq == 0
    assert len(nested_errors) == 1
    assert session.seq == 1  # 嵌套 append 未入日志
    assert session.event_at(0) is outer
    # fire 结束后恢复可 append 状态
    assert session.append("after", {}).seq == 1


# ── observer 失败 contained ──────────────────────────────────────────


def test_observer_failure_contained_and_chain_continues() -> None:
    session = SessionStore().create()
    seen: list[SessionEvent] = []

    def bad_observer(target: SessionProtocol, event: SessionEvent) -> None:
        raise RuntimeError("boom")

    def good_observer(target: SessionProtocol, event: SessionEvent) -> None:
        seen.append(event)

    session.observe(bad_observer)
    session.observe(good_observer)

    event = session.append("x", {"k": 1})

    assert seen == [event]  # 单点失败不打断后续 observer，也不改返回值
    assert session.seq == 1


def test_observer_registered_during_fire_misses_current_event() -> None:
    session = SessionStore().create()
    late_seen: list[SessionEvent] = []

    def late_observer(target: SessionProtocol, event: SessionEvent) -> None:
        late_seen.append(event)

    def registering_observer(target: SessionProtocol, event: SessionEvent) -> None:
        target.observe(late_observer)

    session.observe(registering_observer)
    first = session.append("first", {})
    second = session.append("second", {})

    assert late_seen == [second]  # observer 快照先于入日志：中途注册不收当前事件
    assert first.seq == 0 and second.seq == 1


def test_observe_cancel_is_idempotent() -> None:
    session = SessionStore().create()
    seen: list[SessionEvent] = []
    cancel = session.observe(lambda target, event: seen.append(event))

    session.append("a", {})
    cancel()
    cancel()  # 幂等
    session.append("b", {})

    assert [event.type for event in seen] == ["a"]


# ── request_header 增量 fold ─────────────────────────────────────────


def test_request_header_fold_incremental() -> None:
    session = SessionStore().create()
    assert session.request_header() is None

    session.append("spine.turn.started", {"turn": 1})  # 非 header 事件被 skip
    assert session.request_header() is None

    session.append(REQUEST_HEADER, _header_payload(system="sys-v1"))
    first = session.request_header()
    assert isinstance(first, EpochHeader)
    assert first.system == "sys-v1"
    assert first.config == {"provider": "p", "model": "m1"}
    assert len(first.tools) == 1

    assert session.request_header() is first  # 无新事件：O(1) 返回缓存

    session.append("spine.tool.called", {"tool": "t1"})  # 无关事件不触发重算
    assert session.request_header() is first

    session.append(REQUEST_HEADER, _header_payload(system="sys-v2", model="m2"))
    second = session.request_header()
    assert second is not first
    assert second.system == "sys-v2"
    assert second.config == {"provider": "p", "model": "m2"}

    # 增量 fold 与全量 fold 字节级一致（foldRequestHeader(snapshot) 对位）
    full = foldRequestHeader(session.snapshot_events())
    assert full is not None
    assert headerEquals(full, second)


# ── SessionStore 生命周期 ────────────────────────────────────────────


def test_store_duplicate_id_rejected() -> None:
    store = SessionStore()
    store.create("s1")
    with pytest.raises(ValueError, match="已存在"):
        store.create("s1")


def test_store_auto_ids_skip_collisions() -> None:
    store = SessionStore()
    store.create("session-2")  # 占用自动发号路径的候选值
    assert store.create().id == "session-1"
    assert store.create().id == "session-3"  # 跳过已占用的 session-2


def test_store_dispose_removes_live_entry() -> None:
    store = SessionStore()
    session = store.create("s1")
    session.append("x", {})

    assert store.dispose("s1") is True
    assert store.get("s1") is None
    assert store.dispose("s1") is False  # 重复 dispose 不抛

    # detached session 仍可读写自身日志
    assert session.append("y", {}).seq == 1


def test_store_list_keeps_creation_order() -> None:
    store = SessionStore()
    a = store.create("a")
    b = store.create("b")
    assert store.list() == (a, b)
    store.dispose("a")
    assert store.list() == (b,)


# ── plugin 装配 ─────────────────────────────────────────────────────


async def test_setup_provides_session_store() -> None:
    from lca.plugins.session.runtime.plugin import Config
    from lca.plugins.session.runtime.plugin import setup as plugin_setup

    captured: dict[str, Any] = {}

    class _Ctx:
        """最小 stub PluginContext：审计 provide 即可。"""

        def provide(self, key: Any, value: Any, **_kwargs: Any) -> None:
            captured[str(key)] = value

    setup_fn = getattr(plugin_setup, "setup", plugin_setup)
    assert callable(setup_fn), "@plugin 应暴露 .setup 属性指向原函数"

    await setup_fn(_Ctx(), Config())

    assert "session.store" in captured
    assert isinstance(captured["session.store"], SessionStore)


def test_plugin_manifest_metadata() -> None:
    from lca.harness.plugin_declaration import definition_from_plugin
    from lca.plugins.session.runtime import plugin as plugin_module

    definition = definition_from_plugin(plugin_module.setup, module=__name__)
    assert definition.id == "lca.plugins.session.runtime"
    assert definition.spec.layer == "L2"
    assert "session.store" in definition.provided_capability_keys
    assert definition.required_capability_keys == ()
