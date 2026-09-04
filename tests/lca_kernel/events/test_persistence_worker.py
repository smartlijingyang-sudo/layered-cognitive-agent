"""ADR-0184 PR-2:PersistenceWorker + EventBus.publish_async 测试。

覆盖(plan §PR-2 验证清单 + 测试设计):
- test_persistence_worker_fsync_policy_default:默认 FsyncPolicy.BATCH
- test_persistence_worker_writes_to_spine_sink:enqueue → consumer → sink.append
- test_persistence_worker_flush_for_blocks_until_written:慢 aiter 下 flush_for 阻塞至落盘
- test_persistence_worker_health_snapshot_fields:7 字段齐(含 consumer_running)
- test_persistence_worker_fsync_policy_sync_flushes_per_event:SYNC 策略每条 flush
- test_event_bus_publish_async_routes_through_persistence:EventBus.publish_async
  走 super().publish → PersistenceWorker.flush_for
- test_spine_port_append_async_dispatches_to_persistence:spine_port_append_async
  走 EventBus.publish_async → flush_for
- test_event_spine_append_async_dispatches_to_persistence:同上,EventSpine.append_async 路径
- test_spine_file_sink_uses_mount_sink_not_subscribe:验证 manifest 走 mount_sink
- test_persistence_worker_default_shares_envelope_bus_queue:进程级默认 worker
  与 EnvelopeBus.default() 共享 DeliveryQueue
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
    TeamDelegationCacheHit,
)
from lca_kernel.events.persistence import (
    FsyncPolicy,
    PersistenceHealthSnapshot,
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
