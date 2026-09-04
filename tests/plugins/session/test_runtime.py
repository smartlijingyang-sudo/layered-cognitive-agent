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
    SessionHeader,
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


# ── add_observer_hook（新 Session 接管面）─────────────────────────


def test_store_observer_hook_fanout_on_create() -> None:
    store = SessionStore()
    seen: list[Any] = []
    store.add_observer_hook(seen.append)

    session = store.create("hooked")
    assert seen == [session]


def test_store_observer_hook_fanout_on_restore() -> None:
    store = SessionStore()
    seen: list[Any] = []
    store.add_observer_hook(seen.append)

    restored = store.restore(
        "hooked-restore",
        SessionHeader(version=SESSION_FORMAT_VERSION, id="hooked-restore", created_at=0),
        (),
    )
    assert seen == [restored]


def test_store_observer_hook_cancel_idempotent() -> None:
    store = SessionStore()
    seen: list[Any] = []
    cancel = store.add_observer_hook(seen.append)

    cancel()
    cancel()  # 幂等,不抛
    store.create("after-cancel")
    assert seen == []


def test_store_observer_hook_failure_contained() -> None:
    store = SessionStore()
    good: list[Any] = []

    def bad_hook(session: Any) -> None:
        raise RuntimeError("hook boom")

    store.add_observer_hook(bad_hook)
    store.add_observer_hook(good.append)

    # 单个 hook 抛错不打断其他 hook 与 Session 入仓。
    session = store.create("contained")
    assert store.get("contained") is session
    assert good == [session]


# ── flush（ADR-0186）────────────────────────────────────────────────


async def test_flush_awaits_all_registered_listeners() -> None:
    session = SessionStore().create()
    call_log: list[str] = []

    class ListenerA:
        async def flush(self, target: Any) -> None:
            call_log.append("a")

    class ListenerB:
        async def flush(self, target: Any) -> None:
            call_log.append("b")

    session.register_flush_listener(ListenerA())
    session.register_flush_listener(ListenerB())

    session.append("x", {"k": 1})
    session.append("y", {"k": 2})

    results = await session.flush()

    assert call_log == ["a", "b"]
    assert len(results) == 2
    assert all(r.ok for r in results)
    assert all(r.event_count == 2 for r in results)


async def test_flush_listener_failure_contained() -> None:
    session = SessionStore().create()

    class BadListener:
        async def flush(self, target: Any) -> None:
            raise RuntimeError("boom")

    class GoodListener:
        def __init__(self) -> None:
            self.called = False

        async def flush(self, target: Any) -> None:
            self.called = True

    bad = BadListener()
    good = GoodListener()
    session.register_flush_listener(bad)
    session.register_flush_listener(good)

    results = await session.flush()

    assert len(results) == 2
    assert results[0].ok is False
    assert isinstance(results[0].error, RuntimeError)
    assert results[0].error.args[0] == "boom"
    assert results[1].ok is True
    assert good.called


async def test_flush_duck_types_observer_flush() -> None:
    session = SessionStore().create()
    flush_log: list[int] = []

    class ObserverWithFlush:
        def __call__(self, target: Any, event: Any) -> None:
            pass

        async def flush(self, target: Any) -> None:
            flush_log.append(target.seq)

    obs = ObserverWithFlush()
    session.observe(obs)  # type: ignore[arg-type]
    session.append("x", {"k": 1})

    results = await session.flush()

    assert len(results) == 1
    assert results[0].ok is True
    assert flush_log == [1]


async def test_flush_duck_typed_observer_failure_contained() -> None:
    session = SessionStore().create()

    class BadObserverWithFlush:
        def __call__(self, target: Any, event: Any) -> None:
            pass

        async def flush(self, target: Any) -> None:
            raise ValueError("observer flush boom")

    session.observe(BadObserverWithFlush())  # type: ignore[arg-type]

    results = await session.flush()

    assert len(results) == 1
    assert results[0].ok is False
    assert isinstance(results[0].error, ValueError)


async def test_flush_cancel_listener_skips_next_flush() -> None:
    session = SessionStore().create()
    calls = 0

    class CountingListener:
        async def flush(self, target: Any) -> None:
            nonlocal calls
            calls += 1

    listener = CountingListener()
    cancel = session.register_flush_listener(listener)

    await session.flush()
    assert calls == 1

    cancel()
    await session.flush()
    assert calls == 1  # 取消后不再被调用

    cancel()  # 幂等


async def test_flush_with_no_listeners_returns_empty() -> None:
    session = SessionStore().create()
    results = await session.flush()
    assert results == []


async def test_flush_listener_count_reflects_registrations() -> None:
    session = SessionStore().create()
    assert session.flush_listener_count == 0

    class L:
        async def flush(self, target: Any) -> None:
            pass

    cancel = session.register_flush_listener(L())
    assert session.flush_listener_count == 1

    cancel()
    assert session.flush_listener_count == 0


# ── restore（ADR-0186）─────────────────────────────────────────────


def test_restore_seeds_log_without_firing_observers() -> None:
    store = SessionStore()
    header = SessionHeader(version=SESSION_FORMAT_VERSION, id="s-restored", created_at=1000)
    events = [
        SessionEvent(type="a", seq=0, time=1001, data={"k": 1}),
        SessionEvent(type="b", seq=1, time=1002, data={"k": 2}),
    ]

    session = store.restore("s-restored", header, events)

    # observer 在 seed 期间不应被 fire（本 session 未注册 observer，
    # 后续 append 也只触发新事件）
    seen: list[SessionEvent] = []
    session.observe(lambda target, event: seen.append(event))

    # restore 后状态：
    assert session.seq == 2
    assert session.event_count == 2
    assert session.header.is_seeded is True
    assert session.snapshot_events() == tuple(events)
    assert session.event_at(0) is events[0]
    assert session.event_at(1) is events[1]

    # append 新事件：observer 只收新事件，不收 seed 事件
    new_event = session.append("c", {"k": 3})
    assert new_event.seq == 2
    assert seen == [new_event]


def test_restore_sets_is_seeded_even_when_header_says_false() -> None:
    store = SessionStore()
    header = SessionHeader(
        version=SESSION_FORMAT_VERSION, id="s-seeded", created_at=2000, is_seeded=False
    )
    events = [SessionEvent(type="x", seq=0, time=2001, data={})]

    session = store.restore("s-seeded", header, events)

    # 无论传入 header.is_seeded 值如何，restore 后强制 True
    assert session.header.is_seeded is True


def test_restore_empty_events_is_still_seeded() -> None:
    store = SessionStore()
    header = SessionHeader(version=SESSION_FORMAT_VERSION, id="s-empty", created_at=3000)

    session = store.restore("s-empty", header, [])

    assert session.seq == 0
    assert session.header.is_seeded is True
    assert session.snapshot_events() == ()


def test_restore_with_header_events_initializes_fold() -> None:
    store = SessionStore()
    header = SessionHeader(version=SESSION_FORMAT_VERSION, id="s-fold", created_at=4000)
    header_event = SessionEvent(
        type=REQUEST_HEADER,
        seq=0,
        time=4001,
        data=_header_payload(system="restored-sys", model="m-restored"),
    )

    session = store.restore("s-fold", header, [header_event])

    folded = session.request_header()
    assert folded is not None
    assert folded.system == "restored-sys"
    assert folded.config == {"provider": "p", "model": "m-restored"}

    # 新 header 事件覆盖：增量 fold 接续正确
    session.append(REQUEST_HEADER, _header_payload(system="sys-v2", model="m2"))
    new_fold = session.request_header()
    assert new_fold is not None
    assert new_fold.system == "sys-v2"


def test_store_restore_rejects_duplicate_id() -> None:
    store = SessionStore()
    store.create("dup")
    header = SessionHeader(version=SESSION_FORMAT_VERSION, id="dup", created_at=5000)
    with pytest.raises(ValueError, match="已存在"):
        store.restore("dup", header, [])


def test_store_restore_rejects_header_id_mismatch() -> None:
    store = SessionStore()
    header = SessionHeader(version=SESSION_FORMAT_VERSION, id="other", created_at=6000)
    with pytest.raises(ValueError, match="不一致"):
        store.restore("target", header, [])


def test_store_restore_rejects_discontinuous_seq() -> None:
    store = SessionStore()
    header = SessionHeader(version=SESSION_FORMAT_VERSION, id="bad-seq", created_at=7000)
    events = [
        SessionEvent(type="a", seq=0, time=1, data={}),
        SessionEvent(type="b", seq=2, time=2, data={}),  # 跳 seq
    ]
    with pytest.raises(ValueError, match="seq 不连续"):
        store.restore("bad-seq", header, events)


def test_store_restore_appears_in_get_and_list() -> None:
    store = SessionStore()
    header = SessionHeader(version=SESSION_FORMAT_VERSION, id="listed", created_at=8000)
    session = store.restore("listed", header, [])
    assert store.get("listed") is session
    assert session in store.list()


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


class _FacadeProducer:
    """publisher marker；facade 不入日志。"""


def _hit(*, role: str = "worker") -> Any:
    from lca.contracts.event import TeamDelegationCacheHit

    return TeamDelegationCacheHit(callee_role=role, subtask="t", step=1)


def test_bus_facade_append_maps_payload_into_session_log() -> None:
    from lca.plugins.session.runtime.bus_facade import SessionBusFacade
    from lca_kernel.events.payloads import SpineEventPayload

    session = SessionStore().create("s-bus")
    facade = SessionBusFacade(session)

    hit = _hit()
    ref = facade.append(hit, producer=_FacadeProducer)
    assert ref.event_id == "s-bus:0"
    assert ref.category == "team.delegation.cache_hit"
    event = session.event_at(0)
    assert event is not None
    assert event.type == "team.delegation.cache_hit"
    assert event.data == {"callee_role": "worker", "subtask": "t", "step": 1}

    spine = SpineEventPayload(
        execution_point="brain.perceive.start",
        channel="fact",
        payload={"state_id": "s1"},
    )
    spine_ref = facade.append(spine, producer=_FacadeProducer)
    assert spine_ref.category == "spine.cognition.brain.perceive.start"
    spine_event = session.event_at(1)
    assert spine_event is not None
    assert spine_event.type == "spine.cognition.brain.perceive.start"
    assert spine_event.data["execution_point"] == "brain.perceive.start"
    assert spine_event.data["payload"] == {"state_id": "s1"}
    assert "category" not in spine_event.data


def test_bus_facade_observe_projects_original_payload_and_ref() -> None:
    from lca.plugins.session.runtime.bus_facade import SessionBusFacade

    session = SessionStore().create("s-obs")
    publish = SessionBusFacade(session)
    observe = SessionBusFacade(session)
    seen: list[tuple[Any, Any]] = []

    observe.observe(_FacadeProducer, lambda payload, ref: seen.append((payload, ref)))

    payload = _hit()
    ref = publish.append(payload, producer=_FacadeProducer)

    assert len(seen) == 1
    assert seen[0][0] is payload
    assert seen[0][1] == ref


def test_bus_facade_observe_contains_callback_failure() -> None:
    from lca.plugins.session.runtime.bus_facade import SessionBusFacade

    session = SessionStore().create("s-contain")
    facade = SessionBusFacade(session)
    seen: list[Any] = []

    def boom(payload: Any, ref: Any) -> None:
        del payload, ref
        raise RuntimeError("boom")

    facade.observe(_FacadeProducer, boom)
    facade.observe(_FacadeProducer, lambda payload, ref: seen.append(payload))

    payload = _hit()
    ref = facade.append(payload, producer=_FacadeProducer)

    assert seen == [payload]
    assert ref.event_id == "s-contain:0"
    assert session.seq == 1


def test_as_bus_facade_wraps_session_only() -> None:
    from lca.plugins.session.runtime.bus_facade import SessionBusFacade, as_bus_facade

    session = SessionStore().create("s-coerce")
    wrapped = as_bus_facade(session)
    assert isinstance(wrapped, SessionBusFacade)
    assert wrapped.session is session
    assert as_bus_facade(wrapped) is wrapped
    assert as_bus_facade(None) is None

    class Stub:
        def append(self, payload: Any, *, producer: Any) -> Any:
            del payload, producer
            return None

    stub = Stub()
    assert as_bus_facade(stub) is stub
