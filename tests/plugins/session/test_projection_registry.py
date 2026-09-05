"""ProjectionRegistry plugin 测试（模块②，DSH session-projection 对照）。

覆盖契约：

- 注册 / 引用计数取消（同 key 共享单元，版本失配拒绝，幂等取消）
- 急切驱动（Session.observe 单订阅，逐事件穿全部单元）
- 迟到注册从 ``session.snapshot_events()`` 折历史
- ``apply`` 返回 ``==`` 状态视为无变化，不触发变更订阅
- 单元 ``apply`` 抛错 contained（不波及其他单元、不反噬 append）
- snapshot 完整值 + ``as_of_seq`` 水位；host-only 单元不进 snapshot
- checkpoint / restore 往返（版本失配弃行重折、seq 断裂 fail-loud）
- observer 无 ``flush`` 面（``Session.flush`` 链不探测）
- plugin 装配：provides session.projections、挂活 Session + 未来 Session
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.contracts.protocols.session.projection_unit import ProjectionCheckpoint
from lca.plugins.session.projection_registry import projection_registry as plugin_module
from lca.plugins.session.projection_registry.projection_registry import (
    Config,
    ProjectionRegistry,
    setup,
)
from lca.plugins.session.runtime.store import SessionStore
from lca_kernel.events.session import SessionHeader

# ── 测试单元 ──────────────────────────────────────────────────────────


class _CounterUnit:
    """客户端可见计数单元：``inc.v1`` +1，其余事件返回同一引用。"""

    key = "counter"
    state_version = 1

    def init(self, header: Any) -> dict[str, Any]:
        del header
        return {"count": 0}

    def apply(self, state: dict[str, Any], event: Any) -> dict[str, Any]:
        if event.type != "inc.v1":
            return state
        return {"count": state["count"] + 1}

    def view(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"count": state["count"]}


class _HostOnlyUnit:
    """host-only 单元：无 ``view``，不进 snapshot，但进 checkpoint。"""

    key = "host_only"
    state_version = 1

    def init(self, header: Any) -> dict[str, Any]:
        del header
        return {"seen": 0}

    def apply(self, state: dict[str, Any], event: Any) -> dict[str, Any]:
        if event.type != "inc.v1":
            return state
        return {"seen": state["seen"] + 1}


class _BoomUnit:
    """apply 恒抛错的单元（验证 contained 语义）。"""

    key = "boom"
    state_version = 1

    def init(self, header: Any) -> dict[str, Any]:
        del header
        return {"n": 0}

    def apply(self, state: dict[str, Any], event: Any) -> dict[str, Any]:
        del event
        msg = "boom unit always fails"
        raise RuntimeError(msg)

    def view(self, state: dict[str, Any]) -> dict[str, Any]:
        return dict(state)


def _fake_ctx(store: Any | None) -> Any:
    """最小 stub PluginContext：provide + soft_get。"""

    class _Ctx:
        def __init__(self) -> None:
            self.provided: dict[str, Any] = {}
            self._store = store

        def provide(self, key: Any, value: Any, **_kwargs: Any) -> None:
            self.provided[str(key)] = value

        def soft_get(self, key: str) -> Any | None:
            return self._store if key == "session.store" else None

    return _Ctx()


def _make() -> tuple[ProjectionRegistry, Any]:
    store = SessionStore()
    session = store.create("s1")
    registry = ProjectionRegistry()
    registry.register_to(session)
    return registry, session


# ── 注册 / 取消 ──────────────────────────────────────────────────────


def test_register_and_cancel() -> None:
    registry, session = _make()
    dispose = registry.register(_CounterUnit())
    session.append("inc.v1", {})
    assert registry.state_of(session, "counter") == {"count": 1}

    dispose()
    assert registry.state_of(session, "counter") is None
    assert registry.snapshot(session).values == {}


def test_register_refcount_shared_key() -> None:
    registry, session = _make()
    dispose_a = registry.register(_CounterUnit())
    dispose_b = registry.register(_CounterUnit())
    session.append("inc.v1", {})
    assert registry.state_of(session, "counter") == {"count": 1}

    dispose_a()  # 还有 b 持有，key 仍在
    assert registry.state_of(session, "counter") == {"count": 1}
    dispose_b()  # 最后一个，移除
    assert registry.state_of(session, "counter") is None
    dispose_b()  # 幂等


def test_register_version_mismatch_raises() -> None:
    registry, _ = _make()
    registry.register(_CounterUnit())

    class _V2(_CounterUnit):
        state_version = 2

    with pytest.raises(ValueError, match="state_version"):
        registry.register(_V2())


def test_register_invalid_key_or_version() -> None:
    registry, _ = _make()

    class _BadKey(_CounterUnit):
        key = ""

    class _BadVersion(_CounterUnit):
        state_version = -1

    with pytest.raises(ValueError, match="key"):
        registry.register(_BadKey())
    with pytest.raises(ValueError, match="state_version"):
        registry.register(_BadVersion())


def test_state_version_of() -> None:
    registry, _ = _make()
    assert registry.state_version_of("counter") is None
    registry.register(_CounterUnit())
    assert registry.state_version_of("counter") == 1


# ── 驱动 ─────────────────────────────────────────────────────────────


def test_eager_drive_advances_state() -> None:
    registry, session = _make()
    registry.register(_CounterUnit())
    session.append("inc.v1", {})
    session.append("inc.v1", {})
    session.append("other.v1", {})  # 无关事件不计
    assert registry.state_of(session, "counter") == {"count": 2}
    assert registry.snapshot(session).as_of_seq == session.seq - 1


def test_late_registration_folds_history() -> None:
    registry, session = _make()
    session.append("inc.v1", {})
    session.append("inc.v1", {})
    # 事件已入日志后才注册 → 从 snapshot_events() 折历史
    registry.register(_CounterUnit())
    assert registry.state_of(session, "counter") == {"count": 2}
    session.append("inc.v1", {})
    assert registry.state_of(session, "counter") == {"count": 3}


def test_late_attach_observer_folds_history() -> None:
    store = SessionStore()
    session = store.create("late-attach")
    session.append("inc.v1", {})
    registry = ProjectionRegistry()
    registry.register(_CounterUnit())
    registry.register_to(session)  # observer 晚于事件挂入
    assert registry.state_of(session, "counter") == {"count": 1}
    session.append("inc.v1", {})
    assert registry.state_of(session, "counter") == {"count": 2}


def test_same_reference_apply_no_change_notification() -> None:
    registry, session = _make()
    registry.register(_CounterUnit())
    seen: list[tuple[str, Any, int]] = []
    registry.on_changed(lambda s, key, value, seq: seen.append((key, value, seq)))

    session.append("other.v1", {})  # apply 返回同一引用 → 不通知
    assert seen == []
    session.append("inc.v1", {})  # 状态变化 → 通知一次，完整值
    assert seen == [("counter", {"count": 1}, 1)]


def test_on_changed_cancel_idempotent() -> None:
    registry, session = _make()
    registry.register(_CounterUnit())
    seen: list[Any] = []
    dispose = registry.on_changed(lambda s, key, value, seq: seen.append(value))
    session.append("inc.v1", {})
    dispose()
    dispose()
    session.append("inc.v1", {})
    assert len(seen) == 1


def test_unit_apply_error_contained() -> None:
    registry, session = _make()
    registry.register(_BoomUnit())
    registry.register(_CounterUnit())

    event = session.append("inc.v1", {})
    # 不反噬 append：事件照常入日志
    assert event.seq == 0
    assert session.seq == 1
    # boom 抛错被 contained，状态停在 init；counter 不受波及
    assert registry.state_of(session, "boom") == {"n": 0}
    assert registry.state_of(session, "counter") == {"count": 1}
    session.append("inc.v1", {})
    assert registry.state_of(session, "counter") == {"count": 2}


def test_duplicate_attach_does_not_double_fold() -> None:
    store = SessionStore()
    session = store.create("dup")
    registry = ProjectionRegistry()
    registry.register(_CounterUnit())
    registry.register_to(session)
    registry.register_to(session)  # 重复挂入
    session.append("inc.v1", {})
    assert registry.state_of(session, "counter") == {"count": 1}


# ── snapshot / checkpoint / restore ─────────────────────────────────


def test_snapshot_whole_value_and_host_only() -> None:
    registry, session = _make()
    registry.register(_CounterUnit())
    registry.register(_HostOnlyUnit())
    session.append("inc.v1", {})

    snap = registry.snapshot(session)
    assert snap.as_of_seq == 0
    # 完整值出口：只含客户端可见单元；host-only 不进
    assert dict(snap.values) == {"counter": {"count": 1}}
    # host-only 仍可经 state_of / checkpoint 读
    assert registry.state_of(session, "host_only") == {"seen": 1}
    assert set(registry.checkpoint(session)) == {"counter", "host_only"}


def test_snapshot_empty_session_and_keys_filter() -> None:
    registry, session = _make()
    registry.register(_CounterUnit())
    registry.register(_HostOnlyUnit())

    assert registry.snapshot(session).as_of_seq == -1
    assert dict(registry.snapshot(session).values) == {"counter": {"count": 0}}
    assert dict(registry.snapshot(session, keys=["counter"]).values) == {"counter": {"count": 0}}
    assert registry.snapshot(session, keys=["host_only"]).values == {}


def test_checkpoint_detached_from_live_state() -> None:
    registry, session = _make()
    registry.register(_CounterUnit())
    session.append("inc.v1", {})
    rows = registry.checkpoint(session)
    row = rows["counter"]
    assert row.version == 1
    assert row.seq == 0
    # 脱钩拷贝：改动检查点不污染活 cell
    row.state["count"] = 999
    assert registry.state_of(session, "counter") == {"count": 1}


def test_checkpoint_restore_roundtrip() -> None:
    registry, session = _make()
    registry.register(_CounterUnit())
    session.append("inc.v1", {})
    session.append("inc.v1", {})
    rows = registry.checkpoint(session)  # 水位 seq=1, count=2
    session.append("inc.v1", {})  # 活状态推进到 count=3

    result = registry.restore(rows, session.snapshot_events(), session.header)
    assert result.snapshot.as_of_seq == 2
    assert dict(result.snapshot.values) == {"counter": {"count": 3}}
    # 刷新后的行落在日志末端
    assert result.checkpoint["counter"].seq == 2
    assert result.checkpoint["counter"].state == {"count": 3}


def test_restore_version_mismatch_refolds() -> None:
    registry, session = _make()
    registry.register(_CounterUnit())
    session.append("inc.v1", {})
    # 版本失配行整行弃 → 从 init 重折，结果仍正确
    stale = {"counter": ProjectionCheckpoint(version=999, seq=0, state={"count": 99})}
    result = registry.restore(stale, session.snapshot_events(), session.header)
    assert dict(result.snapshot.values) == {"counter": {"count": 1}}


def test_restore_seq_beyond_end_refolds() -> None:
    registry, session = _make()
    registry.register(_CounterUnit())
    session.append("inc.v1", {})
    # 行声称折到日志末端之后（seq 越界）→ 不可用，重折
    beyond = {"counter": ProjectionCheckpoint(version=1, seq=99, state={"count": 5})}
    result = registry.restore(beyond, session.snapshot_events(), session.header)
    assert dict(result.snapshot.values) == {"counter": {"count": 1}}


def test_restore_rejects_noncontiguous_events() -> None:
    registry, session = _make()
    registry.register(_CounterUnit())
    session.append("inc.v1", {})
    session.append("inc.v1", {})
    events = session.snapshot_events()
    # 断裂：只给 seq=1 的事件，起始 index 0 处 seq 必须是 0
    with pytest.raises(ValueError, match="contiguous"):
        registry.restore({}, (events[1],), session.header)


def test_restore_from_empty_checkpoint() -> None:
    registry, session = _make()
    registry.register(_CounterUnit())
    session.append("inc.v1", {})
    result = registry.restore({}, session.snapshot_events(), session.header)
    assert dict(result.snapshot.values) == {"counter": {"count": 1}}


# ── observer 无 flush 面 ─────────────────────────────────────────────


async def test_registry_observer_has_no_flush_surface() -> None:
    store = SessionStore()
    session = store.create("noflush")
    registry = ProjectionRegistry()
    registry.register_to(session)
    session.append("inc.v1", {})
    # 投影 observer 无 flush 面 → Session.flush 链不产生它的结果
    results = await session.flush()
    assert results == []


# ── plugin 装配 ──────────────────────────────────────────────────────


async def test_setup_provides_and_attaches() -> None:
    store = SessionStore()
    session = store.create("attach")
    ctx = _fake_ctx(store)
    await setup.setup(ctx, Config())

    assert "session.projections" in ctx.provided
    registry = ctx.provided["session.projections"]
    assert isinstance(registry, ProjectionRegistry)

    registry.register(_CounterUnit())
    session.append("inc.v1", {})
    assert registry.state_of(session, "counter") == {"count": 1}

    # 未来 Session 经 add_observer_hook 接管
    future = store.create("future")
    future.append("inc.v1", {})
    assert registry.state_of(future, "counter") == {"count": 1}


async def test_setup_no_store_does_not_raise() -> None:
    ctx = _fake_ctx(store=None)
    await setup.setup(ctx, Config())
    assert "session.projections" in ctx.provided


async def test_setup_attaches_restored_session_via_hook() -> None:
    from lca_kernel.events.session import SESSION_FORMAT_VERSION

    store = SessionStore()
    ctx = _fake_ctx(store)
    await setup.setup(ctx, Config())
    registry = ctx.provided["session.projections"]
    registry.register(_CounterUnit())

    restored = store.restore(
        "restored",
        SessionHeader(version=SESSION_FORMAT_VERSION, id="restored", created_at=0),
        (),
    )
    restored.append("inc.v1", {})
    assert registry.state_of(restored, "counter") == {"count": 1}


def test_plugin_manifest_metadata() -> None:
    from lca.harness.plugin_declaration import definition_from_plugin

    definition = definition_from_plugin(plugin_module.setup, module=__name__)
    assert definition.id == "lca.plugins.session.projection_registry"
    assert definition.spec.layer == "L2"
    assert "session.projections" in definition.provided_capability_keys
    assert "session.store" in definition.required_capability_keys
    effects = definition.spec.effects
    effects_value = {
        (e.value if hasattr(e, "value") else str(e))
        for e in (effects if isinstance(effects, (list, tuple, set, frozenset)) else (effects,))
    }
    assert "none" in effects_value
