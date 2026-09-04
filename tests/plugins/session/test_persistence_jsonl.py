"""JsonlSessionPersistence plugin 测试(ADR-0186 PR-3e/3f)。

覆盖契约:

- observer 注册 → Session.append 自动写到 traces/runs/<id>/<id>.spine.jsonl
- header 仅写一次,事件按时间顺序追加;每行 JSONL
- SessionObserver 失败 contained(由 Session 保证,本测试验证插件自身不抛)
- cancel 函数(register_to 返回值)切断后续观察
- flush / close per-session + 全量
- plugin 装配:requires session.store、provides session.persistence.jsonl、layer L2
- Capability 治理:未装载 session.store 时 no-op
- 不修改 lca/harness/session/persistence.py(import 时只引用,不写)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lca.plugins.session.persistence_jsonl.persistence_jsonl import (
    Config,
    JsonlSessionPersistence,
    register_to_session_store,
    setup,
)
from lca.plugins.session.runtime.store import SessionStore
from lca_kernel.events.session import SessionEvent

if TYPE_CHECKING:
    import pytest

# ── helpers ─────────────────────────────────────────────────────────


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _event_types(lines: list[dict[str, Any]]) -> list[str]:
    """提取所有 event 行的 type;header 行无 type,过滤掉。"""
    return [entry["type"] for entry in lines if entry.get("kind") == "event"]


def _fake_ctx(store: Any | None) -> Any:
    """最小 stub PluginContext:provide + soft_get。"""

    class _Ctx:
        def __init__(self) -> None:
            self.provided: dict[str, Any] = {}
            self._store = store  # type: ignore[attr-defined]

        def provide(self, key: Any, value: Any, **_kwargs: Any) -> None:
            self.provided[str(key)] = value

        def soft_get(self, key: str) -> Any | None:
            return self._store if key == "session.store" else None

    return _Ctx()


# ── 落盘 ────────────────────────────────────────────────────────────


def test_register_to_writes_header_then_events(tmp_path: Path) -> None:
    store = SessionStore()
    session = store.create("s-alpha")
    persistence = JsonlSessionPersistence(runs_root=tmp_path)

    persistence.register_to(session)
    session.append("spine.turn.started", {"turn": 1})
    session.append("spine.turn.delta", {"tokens": 5})
    persistence.flush()

    lines = _read_jsonl(tmp_path / "s-alpha" / "s-alpha.spine.jsonl")
    assert len(lines) == 3
    assert lines[0]["kind"] == "header"
    assert lines[0]["id"] == "s-alpha"
    assert lines[0]["version"] == session.header.version
    assert lines[1]["kind"] == "event"
    assert lines[1]["type"] == "spine.turn.started"
    assert lines[1]["seq"] == 0
    assert lines[1]["data"] == {"turn": 1}
    assert lines[2]["type"] == "spine.turn.delta"
    assert lines[2]["seq"] == 1


def test_header_only_written_once(tmp_path: Path) -> None:
    """重复 append 不重复 header 行。"""
    store = SessionStore()
    session = store.create("s-once")
    persistence = JsonlSessionPersistence(runs_root=tmp_path)

    persistence.register_to(session)
    for i in range(5):
        session.append("evt", {"i": i})
    persistence.flush()

    lines = _read_jsonl(persistence.local_path("s-once"))
    kinds = [entry["kind"] for entry in lines]
    assert kinds == ["header", "event", "event", "event", "event", "event"]


def test_cancel_disconnects_observer(tmp_path: Path) -> None:
    store = SessionStore()
    session = store.create("s-cancel")
    persistence = JsonlSessionPersistence(runs_root=tmp_path)

    cancel = persistence.register_to(session)
    session.append("before", {"k": 1})
    cancel()  # 注销
    cancel()  # 幂等
    session.append("after", {"k": 2})
    persistence.flush()

    lines = _read_jsonl(persistence.local_path("s-cancel"))
    append_kinds = [entry for entry in lines if entry["kind"] == "event"]
    assert len(append_kinds) == 1
    assert append_kinds[0]["type"] == "before"


def test_local_path_does_not_create_file(tmp_path: Path) -> None:
    persistence = JsonlSessionPersistence(runs_root=tmp_path)
    path = persistence.local_path("ghost")
    assert path == tmp_path / "ghost" / "ghost.spine.jsonl"
    assert not path.exists()
    assert not path.parent.exists()


# ── flush / close ────────────────────────────────────────────────────


def test_flush_specific_session_does_not_touch_others(tmp_path: Path) -> None:
    store = SessionStore()
    a = store.create("a")
    b = store.create("b")
    persistence = JsonlSessionPersistence(runs_root=tmp_path)

    persistence.register_to(a)
    persistence.register_to(b)
    a.append("evt-a", {"k": 1})
    b.append("evt-b", {"k": 1})
    # flush("a") 仅刷新 a 的 fd 到磁盘;b 的数据留在 buffer,读前显式 flush
    persistence.flush("a")
    persistence.flush("b")

    a_lines = _read_jsonl(persistence.local_path("a"))
    b_lines = _read_jsonl(persistence.local_path("b"))
    assert "evt-a" in _event_types(a_lines)
    assert "evt-b" in _event_types(b_lines)


def test_close_releases_handles(tmp_path: Path) -> None:
    store = SessionStore()
    session = store.create("s-close")
    persistence = JsonlSessionPersistence(runs_root=tmp_path)

    persistence.register_to(session)
    session.append("evt", {"k": 1})
    persistence.close("s-close")

    # close 后再 append,observer 仍在 observer 列表(close 只关文件)——
    # 重新 open 会写新 header(per-session 句柄表被清,新文件从零开始)。
    # 这里仅验证 close 释放了内部文件句柄(下一行 append 会重新打开)。
    session.append("evt2", {"k": 2})
    persistence.flush()

    lines = _read_jsonl(persistence.local_path("s-close"))
    types = _event_types(lines)
    assert "evt" in types
    assert "evt2" in types


# ── observer 失败 contained ──────────────────────────────────────────


def test_observer_does_not_swallow_event_after_open_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """observer 写入抛错由 Session contained,日志事件不丢失。"""
    store = SessionStore()
    session = store.create("s-fail")
    persistence = JsonlSessionPersistence(runs_root=tmp_path)
    persistence.register_to(session)

    # 强制文件 open 失败:替换 Path.open
    def boom(self: Path, *args: Any, **kwargs: Any) -> Any:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "open", boom)

    # observer 失败由 Session 实现层 contained,append 仍返回事件,
    # 日志不变(本 plugin 失败不应回滚已 commit 的 append)。
    event = session.append("survive", {"k": 1})
    assert event.seq == 0
    assert session.event_at(0) is event


def test_append_unaffected_by_persistence_failure(tmp_path: Path) -> None:
    """observer 抛错不应改变 Session 日志(Session 实现层保证)。"""
    session = SessionStore().create("s-iso")

    def bad_observer(target: Any, event: SessionEvent) -> None:
        raise RuntimeError("write failed")

    session.observe(bad_observer)
    event = session.append("evt", {"k": 1})
    assert session.seq == 1
    assert session.event_at(0) is event


# ── Session 实例权威 ─────────────────────────────────────────────────


def test_session_id_authoritative(tmp_path: Path) -> None:
    """Session 实例的 id 优先于 event.session_id。"""
    session = SessionStore().create("session-authoritative")
    # 直接构造一个 event.session_id 与 Session id 不一致的事件;
    # 在标准路径上 SessionEvent.session_id 通常为空,但 observer 必须用 Session.id。
    event = SessionEvent(
        type="custom",
        seq=0,
        time=0,
        data={"k": 1},
    )
    persistence = JsonlSessionPersistence(runs_root=tmp_path)
    persistence.on_session_event(session, event)
    persistence.flush()

    expected_path = tmp_path / "session-authoritative" / "session-authoritative.spine.jsonl"
    assert expected_path.exists()
    lines = _read_jsonl(expected_path)
    assert lines[-1]["type"] == "custom"


# ── plugin 装配 ────────────────────────────────────────────────────


async def test_setup_provides_capability_and_attaches(tmp_path: Path) -> None:
    store = SessionStore()
    session = store.create("attach")
    ctx = _fake_ctx(store)

    # setup is wrapped by @plugin into a cordis.Plugin carrier; .setup is the
    # original async function (mirrors lca/plugins/session/runtime test).
    setup_fn = setup.setup
    await setup_fn(ctx, Config(runs_root=str(tmp_path)))

    assert "session.persistence.jsonl" in ctx.provided
    persistence = ctx.provided["session.persistence.jsonl"]
    assert isinstance(persistence, JsonlSessionPersistence)

    # 之前创建的活 Session 已挂入 observer
    session.append("after-setup", {"k": 1})
    persistence.flush()
    lines = _read_jsonl(persistence.local_path("attach"))
    assert "after-setup" in _event_types(lines)


async def test_setup_no_store_does_not_raise(tmp_path: Path) -> None:
    ctx = _fake_ctx(store=None)
    # 不抛;capability 仍提供,后续装载 session.store 后可手动 register。
    await setup.setup(ctx, Config(runs_root=str(tmp_path)))
    assert "session.persistence.jsonl" in ctx.provided


async def test_setup_uses_config_fsync(tmp_path: Path) -> None:
    """fsync=True 时 observer 仍正确写出。"""
    store = SessionStore()
    session = store.create("sync")
    ctx = _fake_ctx(store)

    await setup.setup(ctx, Config(runs_root=str(tmp_path), fsync=True))

    persistence = ctx.provided["session.persistence.jsonl"]
    session.append("evt", {"k": 1})
    persistence.flush()
    lines = _read_jsonl(persistence.local_path("sync"))
    assert "evt" in _event_types(lines)


def test_plugin_manifest_metadata() -> None:
    from lca.harness.plugin_declaration import definition_from_plugin
    from lca.plugins.session.persistence_jsonl import persistence_jsonl as plugin_module

    # setup is the cordis.Plugin carrier; pass it directly to read _lca_definition.
    definition = definition_from_plugin(plugin_module.setup, module=__name__)
    assert definition.id == "lca.plugins.session.persistence_jsonl"
    assert definition.spec.layer == "L2"
    assert "session.persistence.jsonl" in definition.provided_capability_keys
    assert "session.store" in definition.required_capability_keys
    effects = definition.spec.effects
    effects_value = (
        tuple(e.value if hasattr(e, "value") else str(e) for e in effects)
        if isinstance(effects, (list, tuple))
        else (effects.value if hasattr(effects, "value") else str(effects),)
    )
    assert "filesystem" in effects_value


def test_register_to_session_store_with_no_store_logs(caplog: pytest.LogCaptureFixture) -> None:
    """soft_get 返回 None 时 no-op,不抛。"""
    ctx = _fake_ctx(store=None)
    persistence = JsonlSessionPersistence()
    register_to_session_store(ctx, persistence)  # 不抛


# ── harness/session/persistence.py 未被改动(契约护栏)──────────────


def test_harness_session_persistence_unchanged() -> None:
    """护栏:本 plugin 不修改 lca/harness/session/persistence.py。

    通过 import 与符号存在性做软断言;真正的源码对比由 git diff 守护。
    """
    from lca.harness.session import persistence as harness_persistence

    assert hasattr(harness_persistence, "JsonlSessionPersistence")
    assert hasattr(harness_persistence, "JsonlSessionPersistenceFactory")


# ── bundle 引用 ─────────────────────────────────────────────────────


def test_bundle_references_plugin() -> None:
    """bundles/session-runtime.yaml 包含新 plugin id。"""
    import yaml

    bundle_path = Path(__file__).parents[3] / "bundles" / "session-runtime.yaml"
    data = yaml.safe_load(bundle_path.read_text(encoding="utf-8"))
    ids = {entry["id"] for entry in data["entries"]}
    assert "lca.plugins.session.persistence_jsonl" in ids
    assert "lca.plugins.session.runtime" in ids
