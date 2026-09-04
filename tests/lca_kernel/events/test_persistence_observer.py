"""ADR-0186 PR-3e / delete-queue Level 4: PersistenceObserver 同步落盘测试。

覆盖:
- 默认 FsyncProtocol.BATCH
- on_session_event → sink.append
- PER_WRITE 策略每条 flush
- health_snapshot 字段(无队列: queue/pending/enqueued/dropped=0)
- EnvelopeDeliveryObserver 协议 + 失败 contained
- spine_file_sink manifest 走 Session.observe
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from lca.contracts.event import EventPayload
from lca.contracts.observability.fsync import FsyncProtocol
from lca_kernel.events import (
    EnvelopeBus,
    EnvelopeRef,
    PersistenceObserver,
    TeamDelegationCacheHit,
)
from lca_kernel.events import (
    FsyncProtocol as ReexportedFsyncProtocol,
)
from lca_kernel.events.persistence import (
    EnvelopeDeliveryObserver,
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


# ── 1:FsyncProtocol 默认值 ──────────────────────────────────────────────


class TestFsyncProtocol:
    def test_persistence_observer_fsync_policy_default(self) -> None:
        """默认 FsyncProtocol.BATCH(平衡 fsync 节奏)。"""
        observer = PersistenceObserver()
        assert observer.fsync_policy is FsyncProtocol.BATCH
        assert observer.fsync_interval_ms == 50

    def test_kernel_reexport_is_contract_enum(self) -> None:
        """lca_kernel.events re-export 的枚举与契约层同一对象(无双枚举)。"""
        assert ReexportedFsyncProtocol is FsyncProtocol


# ── 2:同步落盘 ───────────────────────────────────────────────────────────


class TestPersistenceObserverWrites:
    def test_persistence_observer_writes_to_spine_sink(self) -> None:
        """on_session_event → StubSink.append。"""
        sink = _StubSink()
        observer = PersistenceObserver(sink=sink, fsync_policy=FsyncProtocol.COMMIT)
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
        observer = PersistenceObserver(sink=sink, fsync_policy=FsyncProtocol.COMMIT)
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
        """PER_WRITE 策略:每条事件 flush 一次。"""
        sink = _StubSink()
        observer = PersistenceObserver(sink=sink, fsync_policy=FsyncProtocol.PER_WRITE)
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
            fsync_policy=FsyncProtocol.BATCH,
            fsync_interval_ms=50,
        )
        snap = observer.health_snapshot()
        assert isinstance(snap, PersistenceHealthSnapshot)
        assert snap.policy is FsyncProtocol.BATCH
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
        observer = PersistenceObserver(sink=sink, fsync_policy=FsyncProtocol.COMMIT)
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
        observer = PersistenceObserver(sink=sink, fsync_policy=FsyncProtocol.COMMIT)
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
        observer = PersistenceObserver(sink=sink, fsync_policy=FsyncProtocol.COMMIT)
        import lca_kernel.events.persistence as persistence_mod

        # 经 __dict__ 取 staticmethod 描述符本体:类属性访问返回解包后的
        # 函数,直接回填会丢 staticmethod 语义,污染后续测试的实例调用。
        original = persistence_mod.PersistenceObserver.__dict__["_build_persistable_record"]

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


# ── EP 标注:缺 execution_point 时按 category 反查(ADR-0184 D7)────────


class _StubSession:
    """``SessionProtocol`` 最小形态:``_map_session_event`` 只读 ``.id``。"""

    def __init__(self, session_id: str) -> None:
        self.id = session_id


class TestExecutionPointLabeling:
    """落盘记录必须可按 EP 查询;typed payload 只带 category 时按反查归一。"""

    def test_session_event_without_ep_derives_from_spine_category(self) -> None:
        """SessionEvent data 无 execution_point → 按 category 反查裸 EP。"""
        from lca_kernel.events.session import SessionEvent

        sink = _StubSink()
        observer = PersistenceObserver(sink=sink, fsync_policy=FsyncProtocol.COMMIT)
        event = SessionEvent(
            type="spine.llm.request.header",
            seq=8,
            time=1_788_512_186_015,
            data={"step_id": "step-001", "reason": "initial"},
        )
        observer(_StubSession("run_ep_label"), event)
        assert len(sink.records) == 1
        record = sink.records[0]
        assert record.execution_point == "llm.request.header"
        assert record.category == "spine.llm.request.header"

    def test_session_event_with_explicit_ep_kept_verbatim(self) -> None:
        """data 携带 execution_point 时原样保留(反查不回退)。"""
        from lca_kernel.events.session import SessionEvent

        sink = _StubSink()
        observer = PersistenceObserver(sink=sink, fsync_policy=FsyncProtocol.COMMIT)
        event = SessionEvent(
            type="spine.cognition.brain.think.start",
            seq=1,
            time=1_788_512_185_000,
            data={"execution_point": "brain.think.start", "state_id": "s"},
        )
        observer(_StubSession("run_ep_keep"), event)
        assert sink.records[0].execution_point == "brain.think.start"

    def test_session_event_non_spine_category_stays_unknown(self) -> None:
        """非 spine category 且无 execution_point → 保持 "unknown"。"""
        from lca_kernel.events.session import SessionEvent

        sink = _StubSink()
        observer = PersistenceObserver(sink=sink, fsync_policy=FsyncProtocol.COMMIT)
        event = SessionEvent(
            type="app.custom.event",
            seq=2,
            time=1_788_512_186_000,
            data={"foo": 1},
        )
        observer(_StubSession("run_ep_unknown"), event)
        assert sink.records[0].execution_point == "unknown"

    def test_typed_spine_payload_without_ep_attr_derives_from_category(self) -> None:
        """typed payload 无 execution_point 属性(model-visible 族形态:
        只携带 ``category`` + typed 字段)→ build_record 按 category
        反查裸 EP(EnvelopeDeliveryObserver 路径)。"""
        from lca.contracts.event import Category

        class _TypedSpinePayload(EventPayload):
            """与 SpineLlmRequestHeaderPayload 同形态:有 category、无
            execution_point 属性、字段经 model_dump 序列化。"""

            category: Category = Category.SPINE_LLM_REQUEST_HEADER
            step_id: str = "step-001"

        sink = _StubSink()
        observer = PersistenceObserver(sink=sink, fsync_policy=FsyncProtocol.COMMIT)
        ref = EnvelopeRef(
            event_id="evt-ep-typed",
            category="spine.llm.request.header",
            trace_id="trc-ep",
            ts=0.0,
        )
        observer.on_session_event(_TypedSpinePayload(), ref)
        assert len(sink.records) == 1
        assert sink.records[0].execution_point == "llm.request.header"
