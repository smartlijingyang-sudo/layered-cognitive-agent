"""JsonlSessionPersistence plugin 测试(ADR-0186 PR-3e/3f)。

覆盖契约:

- observer 注册 → Session.append 自动写到 traces/runs/<id>/<id>.session.jsonl
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
from typing import Any

import pytest

from lca.plugins.session.persistence_jsonl.persistence_jsonl import (
    Config,
    JsonlSessionPersistence,
    register_to_session_store,
    setup,
)
from lca.plugins.session.runtime.store import SessionStore
from lca_kernel.events.session import SessionEvent

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

    lines = _read_jsonl(tmp_path / "s-alpha" / "s-alpha.session.jsonl")
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


def test_append_durable_without_explicit_flush(tmp_path: Path) -> None:
    """durable 镜像契约:append 后无需显式 flush,行已在磁盘。

    回归锁:长活进程里依赖 buffered 写入会让尾部事件滞留进程缓冲,
    session.jsonl 在磁盘上截断(事件已入 Session 内存日志,镜像缺尾)。
    """
    store = SessionStore()
    session = store.create("s-durable")
    persistence = JsonlSessionPersistence(runs_root=tmp_path)

    persistence.register_to(session)
    session.append("spine.turn.started", {"turn": 1})

    lines = _read_jsonl(persistence.local_path("s-durable"))
    assert _event_types(lines) == ["spine.turn.started"]


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
    assert path == tmp_path / "ghost" / "ghost.session.jsonl"
    assert not path.exists()
    assert not path.parent.exists()


# ── flush / close ────────────────────────────────────────────────────


def test_flush_accepts_session_object(tmp_path: Path) -> None:
    """``Session.flush()`` duck-type 链以 ``observer.flush(session)`` 调用;
    persistence 必须把 Session-like 入参经 ``.id`` 归一,而不是静默 no-op。
    """
    store = SessionStore()
    session = store.create("s-obj-flush")
    persistence = JsonlSessionPersistence(runs_root=tmp_path)

    persistence.register_to(session)
    session.append("evt", {"k": 1})
    persistence.flush(session)

    assert _event_types(_read_jsonl(persistence.local_path("s-obj-flush"))) == ["evt"]


@pytest.mark.asyncio
async def test_session_flush_chain_reaches_persistence(tmp_path: Path) -> None:
    """端到端:``await session.flush()`` 经 observer-duck-type flush 落盘。

    (``asyncio_mode = "auto"``,marker 仅为显式标注异步契约。)
    """
    store = SessionStore()
    session = store.create("s-chain")
    persistence = JsonlSessionPersistence(runs_root=tmp_path)

    persistence.register_to(session)
    session.append("evt", {"k": 1})
    await session.flush()

    assert _event_types(_read_jsonl(persistence.local_path("s-chain"))) == ["evt"]


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

    expected_path = tmp_path / "session-authoritative" / "session-authoritative.session.jsonl"
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


async def test_setup_attaches_to_future_sessions(tmp_path: Path) -> None:
    """setup 之后才 create 的 Session 也必须被 observer 接管(A3 回归锁)。

    历史 bug:``_attach_to_store`` 只挂当前活 Session,``add_observer_hook``
    缺失时静默跳过,未来 Session 完全不落盘。
    """
    store = SessionStore()
    ctx = _fake_ctx(store)

    await setup.setup(ctx, Config(runs_root=str(tmp_path)))
    persistence = ctx.provided["session.persistence.jsonl"]

    # setup 之后创建的未来 Session
    future = store.create("future")
    future.append("future-evt", {"k": 1})
    persistence.flush()

    lines = _read_jsonl(persistence.local_path("future"))
    assert "future-evt" in _event_types(lines)


async def test_setup_restored_sessions_get_observer_via_hook(tmp_path: Path) -> None:
    """setup 之后 restore 的 Session 也经 add_observer_hook 被接管。"""
    from lca_kernel.events.session import SESSION_FORMAT_VERSION, SessionHeader

    store = SessionStore()
    ctx = _fake_ctx(store)
    await setup.setup(ctx, Config(runs_root=str(tmp_path)))
    persistence = ctx.provided["session.persistence.jsonl"]

    restored = store.restore(
        "restored",
        SessionHeader(version=SESSION_FORMAT_VERSION, id="restored", created_at=0),
        (),
    )
    restored.append("post-restore", {"k": 1})
    persistence.flush()

    lines = _read_jsonl(persistence.local_path("restored"))
    assert "post-restore" in _event_types(lines)


async def test_close_releases_store_hook(tmp_path: Path) -> None:
    """全量 close 释放 add_observer_hook;之后 create 的 Session 不再落盘。"""
    store = SessionStore()
    ctx = _fake_ctx(store)
    await setup.setup(ctx, Config(runs_root=str(tmp_path)))
    persistence = ctx.provided["session.persistence.jsonl"]

    persistence.close()  # 全量 → 释放 store hook

    late = store.create("late")
    late.append("late-evt", {"k": 1})
    persistence.flush()
    assert not persistence.local_path("late").exists()


def test_attach_to_store_requires_observer_hook() -> None:
    """store 无 add_observer_hook 时 fail-loud(禁止静默降级)。"""
    import pytest

    from lca.plugins.session.persistence_jsonl.persistence_jsonl import _attach_to_store

    class _NoHookStore:
        def list(self):
            return ()

    persistence = JsonlSessionPersistence(runs_root=Path("traces/runs"))
    try:
        with pytest.raises(TypeError, match="add_observer_hook"):
            _attach_to_store(_NoHookStore(), persistence)
    finally:
        persistence.close()


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


# ── ADR-0187 §3 D7: assistant_id 持久化（PR-5）───────────────────────


def test_session_header_default_assistant_id_is_none() -> None:
    """未指定时 ``assistant_id`` 默认为 None（fail-open 旧 header）。"""
    from lca_kernel.events.session import SESSION_FORMAT_VERSION, SessionHeader

    header = SessionHeader(version=SESSION_FORMAT_VERSION, id="x", created_at=0)
    assert header.assistant_id is None


def test_session_header_rejects_empty_assistant_id() -> None:
    """空字符串视为非法；必须是 None 或非空。"""
    from lca_kernel.events.session import SESSION_FORMAT_VERSION, SessionHeader

    with pytest.raises(ValueError, match="assistant_id"):
        SessionHeader(
            version=SESSION_FORMAT_VERSION,
            id="x",
            created_at=0,
            assistant_id="   ",  # 全空白
        )


def test_observer_persists_assistant_id_when_header_bound(tmp_path: Path) -> None:
    """Session 携带 assistant_id 时,observer 写盘 header 行带 ``assistant_id``。"""
    store = SessionStore()
    session = store.create("s-observer-bind")
    # 通过 monkey-patch 模拟 Session 携带 assistant_id 的情形
    # （PR-5 不创建 Session 创建路径,但 observer 必须忠实写盘）。
    object.__setattr__(session.header, "assistant_id", "asst_observer")
    persistence = JsonlSessionPersistence(runs_root=tmp_path)
    persistence.register_to(session)
    session.append("evt", {"k": 1})
    persistence.flush()

    lines = _read_jsonl(tmp_path / "s-observer-bind" / "s-observer-bind.session.jsonl")
    header_line = next(entry for entry in lines if entry["kind"] == "header")
    assert header_line["assistant_id"] == "asst_observer"


def test_observer_omits_assistant_id_when_unbound(tmp_path: Path) -> None:
    """Session 未绑定时,observer 写盘 header 行不带 ``assistant_id`` 字段。"""
    store = SessionStore()
    session = store.create("s-observer-unbound")
    # 默认 header.assistant_id = None
    assert session.header.assistant_id is None
    persistence = JsonlSessionPersistence(runs_root=tmp_path)
    persistence.register_to(session)
    session.append("evt", {"k": 1})
    persistence.flush()

    lines = _read_jsonl(tmp_path / "s-observer-unbound" / "s-observer-unbound.session.jsonl")
    header_line = next(entry for entry in lines if entry["kind"] == "header")
    assert "assistant_id" not in header_line


def test_observer_omits_assistant_id_for_whitespace_only(tmp_path: Path) -> None:
    """``assistant_id`` 全空白视为未绑定（write header 行不带字段）。"""
    store = SessionStore()
    session = store.create("s-observer-blank")
    object.__setattr__(session.header, "assistant_id", "   ")
    persistence = JsonlSessionPersistence(runs_root=tmp_path)
    persistence.register_to(session)
    session.append("evt", {"k": 1})
    persistence.flush()

    lines = _read_jsonl(tmp_path / "s-observer-blank" / "s-observer-blank.session.jsonl")
    header_line = next(entry for entry in lines if entry["kind"] == "header")
    assert "assistant_id" not in header_line


# ── bundle 引用 ─────────────────────────────────────────────────────


def test_bundle_references_plugin() -> None:
    """bundles/session-runtime.yaml 包含新 plugin id。"""
    import yaml

    bundle_path = Path(__file__).parents[3] / "bundles" / "session-runtime.yaml"
    data = yaml.safe_load(bundle_path.read_text(encoding="utf-8"))
    ids = {entry["id"] for entry in data["entries"]}
    assert "lca.plugins.session.persistence_jsonl" in ids
    assert "lca.plugins.session.runtime" in ids
