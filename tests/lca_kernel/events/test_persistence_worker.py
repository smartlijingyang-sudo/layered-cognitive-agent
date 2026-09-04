"""ADR-0184 PR-2 + PR-3e:PersistenceObserver + PersistenceWorker 别名测试。

覆盖(plan §PR-2 验证清单 + 测试设计):
- test_persistence_worker_fsync_policy_default:默认 FsyncPolicy.BATCH
- test_persistence_worker_writes_to_spine_sink:enqueue → consumer → sink.append
- test_persistence_worker_flush_for_blocks_until_written:慢 aiter 下 flush_for 阻塞至落盘
- test_persistence_worker_health_snapshot_fields:7 字段齐(含 consumer_running)
- test_persistence_worker_fsync_policy_sync_flushes_per_event:SYNC 策略每条 flush
- test_event_bus_publish_async_routes_through_persistence:EventBus.publish_async
  走 super().publish → PersistenceObserver.flush_for
- test_spine_port_append_async_dispatches_to_persistence:spine_port_append_async
  走 EventBus.publish_async → flush_for
- test_event_spine_append_async_dispatches_to_persistence:同上,EventSpine.append_async 路径
- test_spine_file_sink_uses_mount_sink_not_subscribe:验证 manifest 走 mount_sink
- test_persistence_worker_default_shares_envelope_bus_queue:进程级默认 observer
  与 EnvelopeBus.default() 共享 DeliveryQueue

PR-3e 新增(PersistenceObserver + EnvelopeDeliveryObserver 路径):
- test_persistence_observer_is_session_observer:运行时 isinstance 判定
- test_persistence_observer_on_session_event_writes_to_sink:同步回调直接落盘
- test_persistence_observer_on_session_event_contained_on_sink_failure:失败
  不冒泡、不杀 observer
- test_persistence_observer_on_session_event_contained_on_build_failure:
  build_record 抛错被 contained
- test_persistence_observer_alias_persistence_worker:别名同对象
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from lca.contracts.event import EventPayload
from lca_kernel.events import (
    DeliveryQueue,
    EnvelopeBus,
    EnvelopeRef,
    EventBus,
    EventRef,
    PersistenceObserver,
    TeamDelegationCacheHit,
)
from lca_kernel.events.persistence import (
    EnvelopeDeliveryObserver,
    EnvelopeDeliveryObserver as DirectEnvelopeDeliveryObserver,
    FsyncPolicy,
    PersistenceHealthSnapshot,
    PersistenceObserver as DirectPersistenceObserver,
    PersistenceWorker,
)
from lca_kernel.events.test_catalog import build_test_bus

# ── 公共 helpers ─────────────────────────────────────────────────────────


class _StubSink:
    """``SinkBackend`` 形态的内存 sink —— 收 ``append`` 调,记录 record 列表。"""

    def __init__(self) -> None:
        self.records: list[Any] = []
        self.flush_calls = 0
        self._raise_on_append: BaseException | None = None

    def append(self, record: Any) -> None:
        if self._raise_on_append is not None:
            raise self._raise_on_append
        self.records.append(record)

    def flush(self) -> None:
        self.flush_calls += 1

    def close(self) -> None:
        pass


def _authorized_payload() -> EventPayload:
    return TeamDelegationCacheHit(callee_role="a", subtask="b", step=1)


def _authorized_producer() -> type:
    from lca.plugins.events.publishers.delegation_cache.plugin import (
        DelegationCachePlugin,
    )

    return DelegationCachePlugin


@pytest.fixture(autouse=True)
def _isolate_singletons() -> Any:
    """每个测试清空 EnvelopeBus + PersistenceWorker 进程级单例,避免串扰。"""
    EnvelopeBus.reset_singleton()
    PersistenceWorker.reset_singleton()
    yield
    EnvelopeBus.reset_singleton()
    PersistenceWorker.reset_singleton()


# ── 1:FsyncPolicy 默认值 ────────────────────────────────────────────────


class TestFsyncPolicy:
    def test_persistence_worker_fsync_policy_default(self) -> None:
        """默认 FsyncPolicy.BATCH(平衡 fsync 节奏)。"""
        worker = PersistenceWorker(queue=DeliveryQueue())
        assert worker.fsync_policy is FsyncPolicy.BATCH
        assert worker.fsync_interval_ms == 50


# ── 2:PersistenceWorker 落盘链路 ─────────────────────────────────────────


class TestPersistenceWorkerWrites:
    async def test_persistence_worker_writes_to_spine_sink(self) -> None:
        """enqueue → 后台 consumer → StubSink.append 被调。"""
        sink = _StubSink()
        queue = DeliveryQueue(max_size=128)
        worker = PersistenceWorker(
            sink=sink,
            queue=queue,
            fsync_policy=FsyncPolicy.ASYNC,  # 不 flush 干扰断言
        )
        # 构造 EnvelopeRef + payload 直接 enqueue
        ref = EnvelopeRef(
            event_id="evt-w1",
            category="team.delegation.cache_hit",
            trace_id="trc-1",
            ts=0.0,
        )
        payload = _authorized_payload()
        queue.submit(ref, payload)
        assert queue.depth == 1
        await worker.start()
        # 等落盘
        await worker.flush_for("evt-w1", timeout=2.0)
        assert sink.records and len(sink.records) == 1
        # record 的 event_id 是被 write 的
        record = sink.records[0]
        assert record.event_id == "evt-w1"
        assert record.category == "team.delegation.cache_hit"
        # pending 已清
        assert queue.depth == 0
        await worker.stop()

    async def test_persistence_worker_flush_for_blocks_until_written(self) -> None:
        """无 consumer 启时调 flush_for → consumer 起 + 写到 sink 才解除。"""
        sink = _StubSink()
        queue = DeliveryQueue()
        worker = PersistenceWorker(sink=sink, queue=queue, fsync_policy=FsyncPolicy.ASYNC)
        # 此时 consumer 还没启
        assert worker.consumer_running is False
        ref = EnvelopeRef(
            event_id="evt-w2",
            category="team.delegation.cache_hit",
            trace_id="trc-1",
            ts=0.0,
        )
        queue.submit(ref, _authorized_payload())
        # flush_for 自动起 consumer 并等落盘
        await worker.flush_for("evt-w2", timeout=3.0)
        assert sink.records and sink.records[0].event_id == "evt-w2"
        assert worker.consumer_running is True
        await worker.stop()

    async def test_persistence_worker_fsync_policy_sync_flushes_per_event(self) -> None:
        """SYNC 策略:每条事件 flush 一次。"""
        sink = _StubSink()
        queue = DeliveryQueue()
        worker = PersistenceWorker(sink=sink, queue=queue, fsync_policy=FsyncPolicy.SYNC)
        refs = [
            EnvelopeRef(
                event_id=f"evt-s-{i}",
                category="team.delegation.cache_hit",
                trace_id=f"trc-{i}",
                ts=0.0,
            )
            for i in range(3)
        ]
        for r in refs:
            queue.submit(r, _authorized_payload())
        for r in refs:
            await worker.flush_for(r.event_id, timeout=2.0)
        # SYNC 策略:每条事件过后都 flush,3 条 → flush_calls >= 3
        assert sink.flush_calls >= 3
        await worker.stop()


# ── 3:PersistenceHealthSnapshot ─────────────────────────────────────────


class TestHealthSnapshot:
    def test_persistence_worker_health_snapshot_fields(self) -> None:
        """HealthSnapshot 7 字段齐 + 类型对。"""
        sink = _StubSink()
        queue = DeliveryQueue()
        worker = PersistenceWorker(
            sink=sink,
            queue=queue,
            fsync_policy=FsyncPolicy.BATCH,
            fsync_interval_ms=50,
        )
        snap = worker.health_snapshot()
        assert isinstance(snap, PersistenceHealthSnapshot)
        assert snap.policy is FsyncPolicy.BATCH
        assert snap.queue_depth == 0
        assert snap.pending_count == 0
        assert snap.last_flush_ms is None
        assert snap.enqueued_total == 0
        assert snap.dropped_queue_full == 0
        assert snap.written_total == 0
        assert snap.consumer_running is False


# ── 4:EventBus.publish_async 走 worker ────────────────────────────────────


class TestEventBusPublishAsync:
    async def test_event_bus_publish_async_routes_through_persistence(self) -> None:
        """EventBus.publish_async → super().publish(入队)→ PersistenceWorker.flush_for
        等落盘 → 返回 EventRef.persisted=True。

        技巧:让 ``EnvelopeBus.default()`` 返回带本地 queue 的 bus,从而
        ``PersistenceWorker.default()`` 拿到的是共享该 queue 的 worker;
        这样 publish_async 走 super().publish 把 envelope 入到 worker
        也观察得到的同一个 queue,flush_for 不会饿死。
        """
        bus: EventBus[EventPayload] = build_test_bus()
        # 把本实例注册为 EnvelopeBus 进程级默认 → PersistenceWorker.default
        # 也会拿到同一个 queue。
        EnvelopeBus.set_default(bus)
        # 触发 PersistenceWorker 进程级 default:它会取 EnvelopeBus.default().queue
        worker = PersistenceWorker.default()
        # 用 stub sink 替换 worker 的 sink,这样我们可以断言落盘结果
        # 注意:share_queue 后 worker 已经构造,得替换其内部 _sink
        stub_sink = _StubSink()
        worker._sink = stub_sink  # type: ignore[attr-defined]
        await worker.start()
        ref = await bus.publish_async(_authorized_payload(), producer=_authorized_producer())
        assert isinstance(ref, EventRef)
        assert ref.persisted is True
        # stub sink 收到 1 条 record
        assert len(stub_sink.records) == 1
        # cleanup
        await worker.stop()
        EnvelopeBus.reset_singleton()
        PersistenceWorker.reset_singleton()


# ── 5:spine_port_append_async + EventSpine.append_async ──────────────────


class TestSpineAsyncPaths:
    async def test_spine_port_append_async_dispatches_to_persistence(self) -> None:
        """spine_port_append_async → EventBus.publish_async → worker.flush_for 落盘。

        技巧:必须用 ``EventBus.set_default(bus)`` 而非 ``EnvelopeBus.set_default(bus)``——
        conftest 的 :func:`_reset_singleton` 调用 ``EventBus.reset_singleton()`` 创建
        ``EventBus._default_instance`` 单独 slot,与 ``EnvelopeBus._default_instance``
        不共享(类变量继承语义:写子类创建独立 slot)。``EnvelopeBus.set_default(bus)``
        写不到 ``EventBus._default_instance``,后续 ``EventBus.default()`` 拿到空 cache
        后构造一个无 test catalog 的新 bus,鉴权失败。``PersistenceWorker.default()``
        走 :func:`EnvelopeBus.default()`,所以必须用对应的 :func:`EventBus.set_default`。
        """
        from lca.infrastructure.observability.loop_cursor._spine_port import (
            spine_port_append_async,
        )
        from lca.infrastructure.observability.spine.sinks.base import EventSink

        bus: EventBus[EventPayload] = build_test_bus()
        # 必须用 EventBus.set_default,因为 conftest 的 _reset_singleton 调用
        # EventBus.reset_singleton() 创建 EventBus._default_instance 独立 slot。
        EventBus.set_default(bus)
        EnvelopeBus.set_default(bus)
        worker = PersistenceWorker.default()
        stub_sink = _StubSink()
        worker._sink = stub_sink  # type: ignore[attr-defined]
        await worker.start()

        class _DummySink(EventSink):
            def __init__(self) -> None:
                self.records: list[Any] = []

            def write(self, record: Any) -> None:
                self.records.append(record)

            def close(self) -> None:
                pass

        dummy_sink = _DummySink()
        seen: list[Any] = []

        def _subscriber(record: Any) -> None:
            seen.append(record)

        record = await spine_port_append_async(
            [dummy_sink],
            [_subscriber],
            execution_point="brain.perceive.start",
            channel="fact",
            caller_payload={"state_id": "s1"},
        )
        assert record.execution_point == "brain.perceive.start"
        assert len(seen) == 1
        assert len(stub_sink.records) == 1
        await worker.stop()
        EventBus.reset_singleton()
        EnvelopeBus.reset_singleton()
        PersistenceWorker.reset_singleton()

    async def test_event_spine_append_async_dispatches_to_persistence(self) -> None:
        """EventSpine.append_async → spine_port_append_async → EventBus.publish_async。"""
        from lca.infrastructure.observability.spine.event_spine import EventSpine
        from lca.infrastructure.observability.spine.sinks.base import EventSink

        bus: EventBus[EventPayload] = build_test_bus()
        EventBus.set_default(bus)
        EnvelopeBus.set_default(bus)
        worker = PersistenceWorker.default()
        stub_sink = _StubSink()
        worker._sink = stub_sink  # type: ignore[attr-defined]
        await worker.start()

        class _DummySink(EventSink):
            def __init__(self) -> None:
                self.records: list[Any] = []

            def write(self, record: Any) -> None:
                self.records.append(record)

            def close(self) -> None:
                pass

        dummy_sink = _DummySink()
        spine = EventSpine(sinks=[dummy_sink])
        record = await spine.append_async(
            execution_point="brain.perceive.start",
            channel="fact",
            caller_payload={"state_id": "s1"},
        )
        assert record.execution_point == "brain.perceive.start"
        assert len(stub_sink.records) == 1
        await worker.stop()
        EventBus.reset_singleton()
        EnvelopeBus.reset_singleton()
        PersistenceWorker.reset_singleton()


# ── 6:spine_file_sink manifest 走 mount_sink ─────────────────────────────


class TestSpineFileSinkManifest:
    def test_spine_file_sink_uses_mount_sink_not_subscribe(self) -> None:
        """验证 PR-2:spine_file_sink setup 走 ``bus.mount_sink``,
        不再 ``bus.subscribe(..., on_event=sink)`` 绕道 SinkBackend Protocol。

        静态检查 — 读 manifest 源码确认关键字形态。
        """

        manifest_path = (
            Path(__file__).resolve().parents[3]
            / "lca"
            / "plugins"
            / "events"
            / "sinks"
            / "spine_file_sink"
            / "manifest.py"
        )
        text = manifest_path.read_text(encoding="utf-8")
        assert "bus_obj.mount_sink(" in text, (
            "spine_file_sink manifest 应在 PR-2 走 mount_sink 形态"
        )
        assert "bus_obj.subscribe(" not in text, (
            "spine_file_sink manifest 不应再走 subscribe(..., on_event=sink) 模拟 sink"
        )


# ── 7:进程级默认 worker 共享 EnvelopeBus.queue ───────────────────────────


class TestDefaultSingleton:
    def test_persistence_worker_default_shares_envelope_bus_queue(self) -> None:
        """``PersistenceWorker.default()`` 必须与 ``EnvelopeBus.default()``
        共享同一 DeliveryQueue 实例,否则 flush_for 永远等不到 enqueue。

        注:本测试需要先 reset conftest 创建的 EventBus._default_instance
        独立 slot —— 直接调 :func:`EventBus.reset_singleton` 与
        :func:`EnvelopeBus.reset_singleton` 把两侧都清空,然后让 worker 重新
        走 :func:`EnvelopeBus.default` (注意:不走 EventBus.default,以免走
        到 EventBus 的独立 cache)。
        """
        EventBus.reset_singleton()
        EnvelopeBus.reset_singleton()
        PersistenceWorker.reset_singleton()
        # 用 EnvelopeBus.default()—— PersistenceWorker.default() 内部也走它。
        bus = EnvelopeBus.default()
        worker = PersistenceWorker.default()
        assert worker.queue is bus.queue


# ── 8:PR-3e PersistenceObserver + EnvelopeDeliveryObserver 协议 ───────────────────


class _RaisingSink:
    """``SinkBackend`` 形态的内存 sink,append 总是抛错。"""

    def __init__(self, exc: BaseException | None = None) -> None:
        self.records: list[Any] = []
        self._exc: BaseException = exc if exc is not None else RuntimeError("sink boom")

    def append(self, record: Any) -> None:
        raise self._exc

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


class TestPersistenceObserver:
    """PR-3e:observer 形态替代 worker 形态;失败 contained。"""

    def test_persistence_observer_is_session_observer(self) -> None:
        """``PersistenceObserver`` 是 :class:`EnvelopeDeliveryObserver` 协议实现。

        用 ``@runtime_checkable`` + ``isinstance`` 验证;``EnvelopeDeliveryObserver``
        通过 ``lca_kernel.events`` 顶层与 ``lca_kernel.events.persistence``
        两条路径 import 必须是同一对象。
        """
        observer = PersistenceObserver(queue=DeliveryQueue())
        assert isinstance(observer, EnvelopeDeliveryObserver)
        assert isinstance(observer, DirectEnvelopeDeliveryObserver)
        assert DirectEnvelopeDeliveryObserver is EnvelopeDeliveryObserver
        assert DirectPersistenceObserver is PersistenceObserver

    def test_persistence_observer_on_session_event_writes_to_sink(self) -> None:
        """``on_session_event`` 同步回调:直接触发 build_record + sink.append。"""
        sink = _StubSink()
        queue = DeliveryQueue()
        observer = PersistenceObserver(sink=sink, queue=queue, fsync_policy=FsyncPolicy.ASYNC)
        ref = EnvelopeRef(
            event_id="evt-o1",
            category="team.delegation.cache_hit",
            trace_id="trc-o1",
            ts=0.0,
        )
        # 同步调:observer.on_session_event 走 build_record → sink.append
        observer.on_session_event(_authorized_payload(), ref)
        assert len(sink.records) == 1
        assert sink.records[0].event_id == "evt-o1"
        assert sink.records[0].category == "team.delegation.cache_hit"
        assert observer.written_total == 1
        # event_id 已记入 written 集合,后续 flush_for 立即返回。
        assert "evt-o1" in observer._written_event_ids

    def test_persistence_observer_on_session_event_contained_on_sink_failure(
        self,
    ) -> None:
        """``sink.append`` 抛错 → observer 吞错,不向外冒泡,自身仍可用。

        对齐 DSH JsonlSessionPersistence:失败 contained;observer 不应进入
        不可用状态。后续 ``on_session_event`` 仍可继续处理下一条 envelope。
        """
        sink = _RaisingSink()
        queue = DeliveryQueue()
        observer = PersistenceObserver(sink=sink, queue=queue, fsync_policy=FsyncPolicy.ASYNC)
        ref = EnvelopeRef(
            event_id="evt-o2-fail",
            category="team.delegation.cache_hit",
            trace_id="trc-o2",
            ts=0.0,
        )
        # 失败 contained:不抛
        observer.on_session_event(_authorized_payload(), ref)
        assert observer.written_total == 0
        # observer 仍可用:换上正常 sink,下一条 envelope 落盘成功
        good_sink = _StubSink()
        observer._sink = good_sink
        ref2 = EnvelopeRef(
            event_id="evt-o2-ok",
            category="team.delegation.cache_hit",
            trace_id="trc-o2",
            ts=0.0,
        )
        observer.on_session_event(_authorized_payload(), ref2)
        assert observer.written_total == 1
        assert len(good_sink.records) == 1
        assert good_sink.records[0].event_id == "evt-o2-ok"

    def test_persistence_observer_on_session_event_contained_on_build_failure(
        self,
    ) -> None:
        """``build_record`` 抛错(不合法 payload) → contained;observer 仍可用。

        ``build_record`` 失败的路径由 :mod:`lca_kernel.events.spine_runtime`
        实装,这里通过 monkeypatch 模拟。observer 应吞错 + 不写 sink +
        计数不增;后续正常 envelope 仍可处理。
        """
        sink = _StubSink()
        queue = DeliveryQueue()
        observer = PersistenceObserver(sink=sink, queue=queue, fsync_policy=FsyncPolicy.ASYNC)
        # monkeypatch:让 build_record 在指定 id 上抛错
        import lca_kernel.events.persistence as persistence_mod

        original = persistence_mod.PersistenceObserver._build_persistable_record

        def _raising(
            payload: EventPayload,
            ref: EnvelopeRef,
        ) -> Any:
            if ref.event_id == "evt-o3-bad":
                raise ValueError("bad envelope")
            return original(payload, ref)

        persistence_mod.PersistenceObserver._build_persistable_record = staticmethod(  # type: ignore[assignment]
            _raising
        )
        try:
            ref_bad = EnvelopeRef(
                event_id="evt-o3-bad",
                category="team.delegation.cache_hit",
                trace_id="trc-o3",
                ts=0.0,
            )
            observer.on_session_event(_authorized_payload(), ref_bad)
            assert observer.written_total == 0
            assert sink.records == []
            ref_ok = EnvelopeRef(
                event_id="evt-o3-ok",
                category="team.delegation.cache_hit",
                trace_id="trc-o3",
                ts=0.0,
            )
            observer.on_session_event(_authorized_payload(), ref_ok)
            assert observer.written_total == 1
            assert len(sink.records) == 1
            assert sink.records[0].event_id == "evt-o3-ok"
        finally:
            persistence_mod.PersistenceObserver._build_persistable_record = original  # type: ignore[assignment]

    def test_persistence_observer_alias_persistence_worker(self) -> None:
        """``PersistenceWorker`` 是 :class:`PersistenceObserver` 的别名。

        直接 import 路径与通过 ``lca_kernel.events.persistence`` 都拿到同一类,
        ``isinstance`` 校验无歧义。30 天窗口内的旧调用方不受影响。
        """
        assert PersistenceWorker is PersistenceObserver
        observer = PersistenceWorker(queue=DeliveryQueue())
        assert isinstance(observer, PersistenceObserver)
        assert isinstance(observer, EnvelopeDeliveryObserver)
        # reset_singleton 走 alias 路径同样清空 _default_instance
        assert PersistenceWorker._default_instance is None
        PersistenceObserver.reset_singleton()
        assert PersistenceWorker._default_instance is None
