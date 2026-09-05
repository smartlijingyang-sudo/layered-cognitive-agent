"""PersistenceObserver —— ADR-0186 PR-3e / session-event-pipeline-spec §4.2。

Write-behind 落盘:``Session.observe`` / :meth:`on_session_event` 把已提交
事件 enqueue 到 :class:`RunWriteBehindRegistry`,由 ``WriteBehindBuffer`` 批量
写 ``<run_id>.spine.jsonl``。无逐条 open/append/fsync;显式 ``Session.flush()``
与 run unbind 负责 drain。

- 实现 :class:`SessionObserver` (``__call__(session, event)``)
- 实现 :class:`EnvelopeDeliveryObserver` (``on_session_event(payload, ref)``)
- 失败 **contained**:映射 / enqueue 失败只记日志 + 通知 ``flush_for``
- 测试可注入 ``SinkBackend`` 走同步 stub 路径(``sink=...`` 非 ``None``)

``PersistenceHealthSnapshot`` 暴露 pending / written 计数给 ``/health``。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

from lca.contracts.observability.fsync import FsyncProtocol
from lca.infrastructure.persistence.run_buffer_registry import RunWriteBehindRegistry

if TYPE_CHECKING:
    from lca.contracts.event import EventPayload
    from lca_kernel.events.bus import EnvelopeRef
    from lca_kernel.events.session import SessionEvent, SessionObserver, SessionProtocol
    from lca_kernel.events.sinks import SinkBackend
    from lca_kernel.events.spine_runtime import SpineEventRecord

log = logging.getLogger(__name__)


# ── 公开 Protocol ────────────────────────────────────────────────────────


@runtime_checkable
class EnvelopeDeliveryObserver(Protocol):
    """Session 事件 observer 协议(ADR-0184 PR-3e / DSH JsonlSessionPersistence 形态)。

    实现者承诺:
    - 接收 ``(payload, ref)`` 后**同步**完成自己的派生 / 落盘工作。
    - 失败**contained**:记录 + drain,不向 caller 上抛(observer 失败
      不应杀 Session 主循环;对齐 DSH ``session-persistence-jsonl`` 行为)。
    - 同一 ``ref.event_id`` 重复回调**幂等**;实现可依赖内部
      ``written_event_ids`` 去重。

    设计意图:与 DSH ``onEvent()`` 形态一致,让 SessionBus 之类组件无须关心
    observer 内部实现细节。
    """

    def on_session_event(
        self,
        payload: EventPayload,
        ref: EnvelopeRef,
    ) -> None: ...


# SessionEvent.data 里若携带这些键,视为信封字段而非 inner payload。
_SESSION_EVENT_ENVELOPE_KEYS: frozenset[str] = frozenset(
    {"event_id", "trace_id", "execution_point", "channel", "payload", "prev_event_hash"}
)


@dataclass(frozen=True, slots=True)
class _MappedSessionPayload:
    """SessionEvent → build_record 的鸭子 payload(非公开 EventPayload 子类)。

    ``build_record`` 只读 ``execution_point`` / ``channel`` / ``payload`` /
    ``prev_event_hash``;Session 事件词表开放,不能强制 :class:`Category`。
    """

    execution_point: str
    channel: str
    payload: dict[str, Any]
    prev_event_hash: str | None = None


def _map_session_event(
    session: SessionProtocol,
    event: SessionEvent,
) -> tuple[_MappedSessionPayload, EnvelopeRef]:
    """Best-effort SessionEvent → (payload, EnvelopeRef)。

    映射规则(缺字段用稳定默认,不抛):

    - ``event_id``: ``data.event_id`` 非空,否则 ``{session.id}:{event.seq}``
    - ``trace_id``: ``data.trace_id`` 非空,否则 ``session.id``
    - ``category``: ``event.type``
    - ``execution_point``: ``data.execution_point`` 非空;缺失时按
      ``event.type``(category)反查裸 EP;仍无则 ``"unknown"``
    - ``ts``: ``event.time`` 毫秒 → 秒
    - inner payload: ``data.payload`` 若为 dict,否则去掉信封键后的 ``data``
    """
    from lca_kernel.events.bus import EnvelopeRef

    data = event.data
    raw_id = data.get("event_id")
    event_id = str(raw_id) if raw_id not in (None, "") else f"{session.id}:{event.seq}"
    raw_trace = data.get("trace_id")
    trace_id = str(raw_trace) if raw_trace not in (None, "") else session.id
    execution_point = data.get("execution_point")
    if not isinstance(execution_point, str) or not execution_point:
        from lca_kernel.events.payloads_spine import category_to_spine_ep

        execution_point = category_to_spine_ep(event.type) or "unknown"
    channel = data.get("channel")
    if not isinstance(channel, str) or not channel:
        channel = "fact"
    nested = data.get("payload")
    if isinstance(nested, dict):
        inner: dict[str, Any] = dict(nested)
    else:
        inner = {k: v for k, v in data.items() if k not in _SESSION_EVENT_ENVELOPE_KEYS}
    raw_hash = data.get("prev_event_hash")
    prev_hash = raw_hash if isinstance(raw_hash, str) else None
    ref = EnvelopeRef(
        event_id=event_id,
        category=event.type,
        trace_id=trace_id,
        ts=event.time / 1000.0,
    )
    payload = _MappedSessionPayload(
        execution_point=execution_point,
        channel=channel,
        payload=inner,
        prev_event_hash=prev_hash,
    )
    return payload, ref


def _spine_record_from_mapped(
    mapped: _MappedSessionPayload,
    ref: EnvelopeRef,
) -> SpineEventRecord:
    """Session 路径:把映射后的 payload/ref 写成 SpineEventRecord,保留 trace_id。"""
    from datetime import datetime

    from lca_kernel.events.spine_runtime import SpineEventRecord

    ts = datetime.fromtimestamp(ref.ts, tz=UTC).isoformat()
    return SpineEventRecord(
        event_id=ref.event_id,
        category=ref.category,
        execution_point=mapped.execution_point,
        channel=mapped.channel,
        payload=dict(mapped.payload),
        ts=ts,
        prev_event_hash=mapped.prev_event_hash,
        trace_id=ref.trace_id,
    )


class PersistenceFlushTimeout(TimeoutError):
    """``flush_for`` 在指定超时内未等到 envelope 落盘。"""

    def __init__(self, event_id: str, timeout_s: float) -> None:
        super().__init__(f"PersistenceObserver.flush_for({event_id!r}) 在 {timeout_s}s 内未落盘")
        self.event_id = event_id
        self.timeout_s = timeout_s


@dataclass(frozen=True, slots=True)
class PersistenceHealthSnapshot:
    """observer 健康快照,供 ``/health`` + ``lca-ops events-delivery --policy`` 投影。"""

    policy: FsyncProtocol
    queue_depth: int
    pending_count: int
    last_flush_ms: int | None
    enqueued_total: int
    dropped_queue_full: int
    written_total: int
    consumer_running: bool


class PersistenceObserver:
    """SessionObserver + EnvelopeDeliveryObserver write-behind 落盘。

    生产路径(``sink=None``):enqueue → :class:`RunWriteBehindRegistry`。
    测试路径(``sink=StubSink``):保留同步 ``append`` 语义。
    """

    _default_instance: ClassVar[PersistenceObserver | None] = None

    def __init__(
        self,
        *,
        sink: SinkBackend | None = None,
        run_dir: Path | None = None,
        fsync_policy: FsyncProtocol = FsyncProtocol.BATCH,
        fsync_interval_ms: int = 50,
        registry: RunWriteBehindRegistry | None = None,
    ) -> None:
        self._sink = sink
        self._run_dir = run_dir
        self._fsync_policy = fsync_policy
        self._fsync_interval_ms = fsync_interval_ms
        self._written_event_ids: set[str] = set()
        self._written_total = 0
        self._last_flush_ms: int | None = None
        self._flush_events: dict[str, asyncio.Event] = {}
        self._registry = registry
        if sink is None and self._registry is None:
            self._registry = RunWriteBehindRegistry.default()

    def _ensure_registry(self) -> RunWriteBehindRegistry:
        if self._registry is None:
            self._registry = RunWriteBehindRegistry.default()
        return self._registry

    def _on_spine_batch_written(self, event_ids: list[str] | tuple[str, ...]) -> None:
        for event_id in event_ids:
            self._written_event_ids.add(event_id)
            self._written_total += 1
            self._notify_flush(event_id)
        registry = self._registry
        if registry is not None:
            self._last_flush_ms = registry.last_flush_ms

    # ── SessionObserver 协议 ─────────────────────────────────────────────

    def __call__(self, session: SessionProtocol, event: SessionEvent) -> None:
        try:
            mapped_payload, ref = _map_session_event(session, event)
            record = _spine_record_from_mapped(mapped_payload, ref)
        except Exception:
            event_id = f"{session.id}:{event.seq}"
            log.exception(
                "session event mapping failed; envelope not persisted",
                extra={
                    "event_id": event_id,
                    "session_id": session.id,
                    "seq": event.seq,
                },
            )
            self._notify_flush(event_id)
            return
        self._persist_record(record, ref.event_id)

    def as_session_observer(self) -> SessionObserver:
        return self

    # ── EnvelopeDeliveryObserver 协议 ────────────────────────────────────

    def on_session_event(
        self,
        payload: EventPayload,
        ref: EnvelopeRef,
    ) -> None:
        try:
            record = self._build_persistable_record(payload, ref)
        except Exception:
            log.exception(
                "build_record failed; envelope not persisted",
                extra={"event_id": ref.event_id},
            )
            self._notify_flush(ref.event_id)
            return
        self._persist_record(record, ref.event_id)

    # ── 进程级单例 ───────────────────────────────────────────────────────

    @classmethod
    def default(cls) -> PersistenceObserver:
        if cls._default_instance is None:
            instance = cls()
            registry = instance._ensure_registry()
            registry._on_spine_batch_written = instance._on_spine_batch_written
            cls._default_instance = instance
        return cls._default_instance

    @classmethod
    def set_default(cls, instance: PersistenceObserver | None) -> None:
        cls._default_instance = instance

    @classmethod
    def reset_singleton(cls) -> None:
        cls._default_instance = None

    @classmethod
    async def stop_default_if_running(cls) -> None:
        return

    # ── 只读属性 ─────────────────────────────────────────────────────────

    @property
    def fsync_policy(self) -> FsyncProtocol:
        return self._fsync_policy

    @property
    def fsync_interval_ms(self) -> int:
        return self._fsync_interval_ms

    @property
    def sink(self) -> SinkBackend | None:
        return self._sink

    @property
    def pending_count(self) -> int:
        if self._sink is not None:
            return 0
        return self._ensure_registry().pending_count()

    @property
    def last_flush_ms(self) -> int | None:
        return self._last_flush_ms

    @property
    def written_total(self) -> int:
        return self._written_total

    @property
    def consumer_running(self) -> bool:
        return False

    def health_snapshot(self) -> PersistenceHealthSnapshot:
        pending = self.pending_count
        return PersistenceHealthSnapshot(
            policy=self._fsync_policy,
            queue_depth=pending,
            pending_count=pending,
            last_flush_ms=self._last_flush_ms,
            enqueued_total=self._written_total + pending,
            dropped_queue_full=0,
            written_total=self._written_total,
            consumer_running=False,
        )

    # ── 生命周期 ────────────────────────────────────────────────────────

    async def start(self) -> None:
        return

    async def stop(self) -> None:
        return

    async def flush(self, session: SessionProtocol | None = None, *, timeout: float = 30.0) -> None:
        """Drain write-behind buffers (Session duck-type flush + explicit API)."""
        self.flush_sync(session.id if session is not None else None)

    def flush_sync(self, run_id: str | None = None) -> None:
        """Synchronous drain for tests and explicit callers."""
        if self._sink is not None:
            self._sink.flush()
            self._last_flush_ms = int(time.time() * 1000)
            return
        registry = self._ensure_registry()
        if run_id is not None:
            registry.flush_run(run_id)
        else:
            registry.flush_all()
        self._last_flush_ms = registry.last_flush_ms

    async def flush_for(self, event_id: str, *, timeout: float = 5.0) -> None:
        if event_id in self._written_event_ids:
            return
        if self._sink is not None:
            event = self._flush_events.get(event_id)
            if event is None:
                event = asyncio.Event()
                self._flush_events[event_id] = event
            try:
                await asyncio.wait_for(event.wait(), timeout=timeout)
            except TimeoutError as exc:
                raise PersistenceFlushTimeout(event_id, timeout) from exc
            return

        registry = self._ensure_registry()
        if event_id not in self._written_event_ids:
            from lca.infrastructure.persistence.run_paths import run_id_from_event_id

            registry.flush_run(run_id_from_event_id(event_id))

        if event_id in self._written_event_ids:
            return

        event = self._flush_events.get(event_id)
        if event is None:
            event = asyncio.Event()
            self._flush_events[event_id] = event
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except TimeoutError as exc:
            raise PersistenceFlushTimeout(event_id, timeout) from exc

    def enqueue_spine_record(self, record: SpineEventRecord) -> None:
        """Public enqueue entry for shim callers (SpineFileSink.append)."""
        self._persist_record(record, record.event_id)

    def _persist_record(self, record: SpineEventRecord, event_id: str) -> None:
        if event_id in self._written_event_ids:
            self._notify_flush(event_id)
            return
        if self._sink is not None:
            self._persist_record_sync(record, event_id)
            return
        try:
            self._ensure_registry().enqueue_spine(record, run_dir=self._run_dir)
        except Exception:
            log.exception(
                "write-behind enqueue failed; envelope not persisted",
                extra={"event_id": event_id},
            )
            self._notify_flush(event_id)
            return
        if self._fsync_policy is FsyncProtocol.COMMIT:
            self._notify_flush(event_id)

    def _persist_record_sync(self, record: SpineEventRecord, event_id: str) -> None:
        sink = self._sink
        if sink is None:
            return
        try:
            sink.append(record)
        except Exception:
            log.exception(
                "sink append failed; envelope not persisted",
                extra={
                    "event_id": event_id,
                    "sink_id": type(self._sink).__name__,
                },
            )
            self._notify_flush(event_id)
            return
        self._written_event_ids.add(event_id)
        self._written_total += 1
        if self._fsync_policy is FsyncProtocol.PER_WRITE:
            sink.flush()
            self._last_flush_ms = int(time.time() * 1000)
        elif self._fsync_policy is FsyncProtocol.BATCH and self._fsync_interval_ms > 0:
            self._maybe_fsync_batched()
        self._notify_flush(event_id)

    def _maybe_fsync_batched(self) -> None:
        sink = self._sink
        if sink is None:
            return
        last = self._last_flush_ms
        now_ms = int(time.time() * 1000)
        if last is None or (now_ms - last) >= self._fsync_interval_ms:
            sink.flush()
            self._last_flush_ms = now_ms

    def _notify_flush(self, event_id: str) -> None:
        event: asyncio.Event | None = self._flush_events.pop(event_id, None)
        if event is not None:
            event.set()

    @staticmethod
    def _build_persistable_record(payload: EventPayload, ref: EnvelopeRef) -> SpineEventRecord:
        from lca_kernel.events.spine_runtime import build_record

        return build_record(payload, ref)

    def __repr__(self) -> str:
        mode = "sync-stub" if self._sink is not None else "write-behind"
        return (
            f"PersistenceObserver(mode={mode!r}, policy={self._fsync_policy.value!r}, "
            f"written_total={self._written_total})"
        )


__all__ = [
    "EnvelopeDeliveryObserver",
    "PersistenceFlushTimeout",
    "PersistenceHealthSnapshot",
    "PersistenceObserver",
]
