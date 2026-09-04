"""ADR-0186 PR-3e / delete-queue Level 4: PersistenceObserver 同步落盘测试。

覆盖:
- 默认 FsyncPolicy.BATCH
- on_session_event → sink.append
- SYNC 策略每条 flush
- health_snapshot 字段(无队列: queue/pending/enqueued/dropped=0)
- EnvelopeDeliveryObserver 协议 + 失败 contained
- spine_file_sink manifest 走 mount_sink
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from lca.contracts.event import EventPayload
from lca_kernel.events import (
    EnvelopeBus,
    EnvelopeRef,
    PersistenceObserver,
    TeamDelegationCacheHit,
)
from lca_kernel.events.persistence import (
    EnvelopeDeliveryObserver,
    FsyncPolicy,
    PersistenceHealthSnapshot,
)
from lca_kernel.events.persistence import (
    EnvelopeDeliveryObserver as DirectEnvelopeDeliveryObserver,
)
from lca_kernel.events.persistence import (
    PersistenceObserver as DirectPersistenceObserver,
)

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


@pytest.fixture(autouse=True)
def _isolate_singletons() -> Any:
    """每个测试清空 EnvelopeBus + PersistenceObserver 进程级单例,避免串扰。"""
    EnvelopeBus.reset_singleton()
    PersistenceObserver.reset_singleton()
    yield
    EnvelopeBus.reset_singleton()
    PersistenceObserver.reset_singleton()


# ── 1:FsyncPolicy 默认值 ────────────────────────────────────────────────


class TestFsyncPolicy:
    def test_persistence_observer_fsync_policy_default(self) -> None:
        """默认 FsyncPolicy.BATCH(平衡 fsync 节奏)。"""
        observer = PersistenceObserver()
        assert observer.fsync_policy is FsyncPolicy.BATCH
        assert observer.fsync_interval_ms == 50


# ── 2:同步落盘 ───────────────────────────────────────────────────────────


class TestPersistenceObserverWrites:
    def test_persistence_observer_writes_to_spine_sink(self) -> None:
        """on_session_event → StubSink.append。"""
        sink = _StubSink()
        observer = PersistenceObserver(sink=sink, fsync_policy=FsyncPolicy.ASYNC)
        ref = EnvelopeRef(
            event_id="evt-w1",
            category="team.delegation.cache_hit",
            trace_id="trc-1",
            ts=0.0,
        )
        observer.on_session_event(_authorized_payload(), ref)
        assert sink.records and len(sink.records) == 1
        record = sink.records[0]
        assert record.event_id == "evt-w1"
        assert record.category == "team.delegation.cache_hit"
        assert observer.pending_count == 0
        assert observer.written_total == 1

    async def test_persistence_observer_flush_for_returns_when_written(self) -> None:
        """flush_for 对已写入 id 立即返回;consumer_running 恒 False。"""
        sink = _StubSink()
        observer = PersistenceObserver(sink=sink, fsync_policy=FsyncPolicy.ASYNC)
        assert observer.consumer_running is False
        ref = EnvelopeRef(
            event_id="evt-w2b",
            category="team.delegation.cache_hit",
            trace_id="trc-1",
            ts=0.0,
        )
        observer.on_session_event(_authorized_payload(), ref)
        await observer.flush_for("evt-w2b", timeout=1.0)
        assert sink.records and sink.records[0].event_id == "evt-w2b"
        assert observer.consumer_running is False

    def test_persistence_observer_fsync_policy_sync_flushes_per_event(self) -> None:
        """SYNC 策略:每条事件 flush 一次。"""
        sink = _StubSink()
        observer = PersistenceObserver(sink=sink, fsync_policy=FsyncPolicy.SYNC)
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
            observer.on_session_event(_authorized_payload(), r)
        assert sink.flush_calls >= 3
        assert observer.written_total == 3


# ── 3:PersistenceHealthSnapshot ─────────────────────────────────────────


class TestHealthSnapshot:
    def test_persistence_observer_health_snapshot_fields(self) -> None:
        """HealthSnapshot 字段齐;无队列相关计数恒 0。"""
        sink = _StubSink()
        observer = PersistenceObserver(
            sink=sink,
            fsync_policy=FsyncPolicy.BATCH,
            fsync_interval_ms=50,
        )
        snap = observer.health_snapshot()
        assert isinstance(snap, PersistenceHealthSnapshot)
        assert snap.policy is FsyncPolicy.BATCH
        assert snap.queue_depth == 0
        assert snap.pending_count == 0
        assert snap.last_flush_ms is None
        assert snap.enqueued_total == 0
        assert snap.dropped_queue_full == 0
        assert snap.written_total == 0
        assert snap.consumer_running is False


# ── 5:spine_file_sink manifest 走 Session.observe 目录 ───────────────────


class TestSpineFileSinkManifest:
    def test_spine_file_sink_uses_session_observe_not_bus(self) -> None:
        """验证 spine_file_sink setup 只经 Session.observe 目录登记，
        不再 ``mount_sink`` / ``bus.subscribe``。
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
        assert "register_as_session_observer(" in text, (
            "spine_file_sink manifest 应走 Session.observe 目录登记"
        )
        assert "bus_obj.mount_sink(" not in text, (
            "spine_file_sink manifest 不应再 mount_sink（ADR-0186 PR-3f）"
        )
        assert "bus_obj.subscribe(" not in text, (
            "spine_file_sink manifest 不应再走 subscribe(..., on_event=sink)"
        )


# ── 6:EnvelopeDeliveryObserver 协议 ─────────────────────────────────────


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


class TestPersistenceObserverProtocol:
    """observer 形态;失败 contained。"""

    def test_persistence_observer_is_envelope_delivery_observer(self) -> None:
        """``PersistenceObserver`` 是 :class:`EnvelopeDeliveryObserver` 协议实现。"""
        observer = PersistenceObserver()
        assert isinstance(observer, EnvelopeDeliveryObserver)
        assert isinstance(observer, DirectEnvelopeDeliveryObserver)
        assert DirectEnvelopeDeliveryObserver is EnvelopeDeliveryObserver
        assert DirectPersistenceObserver is PersistenceObserver

    def test_persistence_observer_on_session_event_writes_to_sink(self) -> None:
        """``on_session_event`` 同步回调:直接触发 build_record + sink.append。"""
        sink = _StubSink()
        observer = PersistenceObserver(sink=sink, fsync_policy=FsyncPolicy.ASYNC)
        ref = EnvelopeRef(
            event_id="evt-o1",
            category="team.delegation.cache_hit",
            trace_id="trc-o1",
            ts=0.0,
        )
        observer.on_session_event(_authorized_payload(), ref)
        assert len(sink.records) == 1
        assert sink.records[0].event_id == "evt-o1"
        assert sink.records[0].category == "team.delegation.cache_hit"
        assert observer.written_total == 1
        assert "evt-o1" in observer._written_event_ids

    def test_persistence_observer_on_session_event_contained_on_sink_failure(
        self,
    ) -> None:
        """``sink.append`` 抛错 → observer 吞错,不向外冒泡,自身仍可用。"""
        sink = _RaisingSink()
        observer = PersistenceObserver(sink=sink, fsync_policy=FsyncPolicy.ASYNC)
        ref = EnvelopeRef(
            event_id="evt-o2-fail",
            category="team.delegation.cache_hit",
            trace_id="trc-o2",
            ts=0.0,
        )
        observer.on_session_event(_authorized_payload(), ref)
        assert observer.written_total == 0
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
        """``build_record`` 抛错 → contained;observer 仍可用。"""
        sink = _StubSink()
        observer = PersistenceObserver(sink=sink, fsync_policy=FsyncPolicy.ASYNC)
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
