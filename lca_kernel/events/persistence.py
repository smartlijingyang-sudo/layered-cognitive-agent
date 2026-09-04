"""PersistenceObserver —— ADR-0186 PR-3e / delete-queue Level 4 落盘 observer。

同步写 :class:`lca_kernel.events.sinks.SinkBackend`(<run_id>.spine.jsonl):
``Session.observe`` / :meth:`on_session_event` 两条入口共享同一 sink + fsync
策略。无投递队列、无后台 consumer。

- 实现 :class:`lca_kernel.events.session.SessionObserver` (``__call__(session, event)``):
  可直接 ``Session.observe(observer)``。SessionEvent 映射为 payload/ref 后写
  同一 sink(保留 ``trace_id``)。
- 实现 :class:`EnvelopeDeliveryObserver` (``on_session_event(payload, ref)``)。
- 失败 ``contained``:单条落盘失败 / build_record / SessionEvent 映射失败仅记
  日志 + 通知 ``flush_for``,不上抛 Session.append(与 DSH 一致)。

责任边界:
- 唯一 ``seq/epoch/hash`` 分配链消费者(经 :mod:`lca.infrastructure.observability.spine.context`
  已在 :mod:`lca_kernel.events.spine_runtime.build_record` 注入,observer 不直接分配)。
- ``fsync_policy``:取契约枚举 :class:`lca.contracts.observability.fsync.FsyncProtocol`
  —— PER_WRITE(每事件 fsync)/ BATCH(50ms 间隔,默认)/ COMMIT(运行期不
  fsync,由 sink.close 决定);Profile 可挂自定义 SinkBackend。
- ``PersistenceHealthSnapshot`` 暴露给 ``/health`` + ``lca-ops events-delivery --policy``;
  无队列后 ``queue_depth`` / ``pending_count`` / ``enqueued_total`` /
  ``dropped_queue_full`` 恒为 0,``consumer_running`` 恒为 False。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

from lca.contracts.observability.fsync import FsyncProtocol

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
        # typed payload(如 model-visible 族)只携带 category、无
        # execution_point 字段 —— 按 category 反查归一为裸 EP,
        # 落盘事件才可被 reader / fold 按 EP 查询(ADR-0184 D7);
        # 非 spine category 才落 "unknown"。
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
    """Session 路径:把映射后的 payload/ref 写成 SpineEventRecord,保留 trace_id。

    ``build_record`` 不透传 ``ref.trace_id``;Session 事件以 session.id 为默认
    trace,必须写进 durable 记录,不能走那条丢失路径。
    """
    from datetime import datetime, timezone

    from lca_kernel.events.spine_runtime import SpineEventRecord

    ts = datetime.fromtimestamp(ref.ts, tz=timezone.utc).isoformat()
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


# ── 公开 enum / dataclass ────────────────────────────────────────────────

# fsync 节奏是契约,定义在 :mod:`lca.contracts.observability.fsync`
# (PER_WRITE / BATCH / COMMIT);本模块只消费,不再私有条目。
# 旧名映射:SYNC → PER_WRITE;ASYNC 无运行期语义差异,归入
# BATCH / COMMIT 按落盘时机二选一。


class PersistenceFlushTimeout(TimeoutError):
    """``flush_for`` 在指定超时内未等到 envelope 落盘。

    单点错误面:caller 接 :class:`TimeoutError` 时区分本类,便于 caller 决定
    是 retry 还是 fail-loud。事件可能已落盘或尚未经 observer 写入。
    """

    def __init__(self, event_id: str, timeout_s: float) -> None:
        super().__init__(f"PersistenceObserver.flush_for({event_id!r}) 在 {timeout_s}s 内未落盘")
        self.event_id = event_id
        self.timeout_s = timeout_s


@dataclass(frozen=True, slots=True)
class PersistenceHealthSnapshot:
    """observer 健康快照,供 ``/health`` + ``lca-ops events-delivery --policy`` 投影。

    无投递队列后 ``queue_depth`` / ``pending_count`` / ``enqueued_total`` /
    ``dropped_queue_full`` 恒为 0;``consumer_running`` 恒为 False。
    """

    policy: FsyncProtocol
    queue_depth: int
    pending_count: int
    last_flush_ms: int | None
    enqueued_total: int
    dropped_queue_full: int
    written_total: int
    consumer_running: bool


# ── 主类 ──────────────────────────────────────────────────────────────────


class PersistenceObserver:
    """SessionObserver + EnvelopeDeliveryObserver 同步落盘(无队列)。

    实现 :class:`SessionObserver`:``Session.observe(observer)`` 在 append 提交后
    调 :meth:`__call__`,内部映射 SessionEvent → payload/ref 再走
    :meth:`on_session_event`。
    实现 :class:`EnvelopeDeliveryObserver`:外部(SyncEventBus / SessionBus 等)
    可直接调 :meth:`on_session_event`。
    两条路径共享同一 sink 写入入口、fsync 策略与计数器。

    进程级单例(:meth:`default`)。
    """

    _default_instance: ClassVar[PersistenceObserver | None] = None

    def __init__(
        self,
        *,
        sink: SinkBackend | None = None,
        fsync_policy: FsyncProtocol = FsyncProtocol.BATCH,
        fsync_interval_ms: int = 50,
    ) -> None:
        from lca_kernel.events.sinks.spine_sink import SpineSink

        self._sink: SinkBackend = sink if sink is not None else SpineSink()
        self._fsync_policy = fsync_policy
        self._fsync_interval_ms = fsync_interval_ms
        self._written_event_ids: set[str] = set()
        self._written_total = 0
        self._last_flush_ms: int | None = None
        self._flush_events: dict[str, asyncio.Event] = {}

    # ── SessionObserver 协议 ─────────────────────────────────────────────

    def __call__(self, session: SessionProtocol, event: SessionEvent) -> None:
        """SessionObserver 入口:``Session.observe(self)`` 注册后,append 提交即调用。

        失败 **contained**:SessionEvent → payload/ref 映射失败只记日志 +
        通知 flush_for,不向 :meth:`SessionProtocol.append` 上抛。落盘失败
        由 :meth:`on_session_event` 同样 contained。

        Args:
            session: 已提交本事件的 Session(日志已含 ``event``)。
            event: 刚入日志的 :class:`SessionEvent`。
        """
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
        """Adapter:本实例作为 :class:`SessionObserver` 交给 ``Session.observe``。

        返回 ``self``(:meth:`__call__` 即 Protocol 入口)。显式方法让注册意图
        可检索,不必把 PersistenceObserver 当裸 callable 传递。
        """
        return self

    # ── EnvelopeDeliveryObserver 协议 ────────────────────────────────────

    def on_session_event(
        self,
        payload: EventPayload,
        ref: EnvelopeRef,
    ) -> None:
        """EnvelopeDeliveryObserver 协议入口(PR-3e / DSH JsonlSessionPersistence 形态)。

        失败 **contained**:build_record / sink.append 抛错仅记日志 +
        通知 flush_for 等待方;不向外冒泡,observer 自身不进入不可用状态。

        Args:
            payload: 已鉴权的 :class:`EventPayload`。
            ref: 对应的 :class:`EnvelopeRef`(event_id / category / trace_id)。
        """
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
        """进程级默认实例。多次调用返回同一对象。"""
        if cls._default_instance is None:
            cls._default_instance = cls()
        return cls._default_instance

    @classmethod
    def set_default(cls, instance: PersistenceObserver | None) -> None:
        cls._default_instance = instance

    @classmethod
    def reset_singleton(cls) -> None:
        """测试隔离:清空默认实例。下次 :meth:`default` 重新构造。"""
        cls._default_instance = None

    @classmethod
    async def stop_default_if_running(cls) -> None:
        """测试隔离 helper:无后台 consumer 后为 no-op,保留调用面。"""
        return

    # ── 只读属性 ─────────────────────────────────────────────────────────

    @property
    def fsync_policy(self) -> FsyncProtocol:
        return self._fsync_policy

    @property
    def fsync_interval_ms(self) -> int:
        return self._fsync_interval_ms

    @property
    def sink(self) -> SinkBackend:
        return self._sink

    @property
    def pending_count(self) -> int:
        """无队列:恒为 0(同步落盘无 pending buffer)。"""
        return 0

    @property
    def last_flush_ms(self) -> int | None:
        """最近一次 fsync 的墙钟毫秒;从未 fsync 时为 None。"""
        return self._last_flush_ms

    @property
    def written_total(self) -> int:
        """本 observer 累计已落盘的 envelope 数(含失败后未补救)。"""
        return self._written_total

    @property
    def consumer_running(self) -> bool:
        """无后台 consumer:恒为 False。"""
        return False

    def health_snapshot(self) -> PersistenceHealthSnapshot:
        return PersistenceHealthSnapshot(
            policy=self._fsync_policy,
            queue_depth=0,
            pending_count=0,
            last_flush_ms=self._last_flush_ms,
            enqueued_total=0,
            dropped_queue_full=0,
            written_total=self._written_total,
            consumer_running=False,
        )

    # ── 生命周期 ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """无后台 consumer:no-op(保留调用面)。"""
        return

    async def stop(self) -> None:
        """无后台 consumer:no-op(保留调用面)。"""
        return

    # ── 同步等接口 ───────────────────────────────────────────────────────

    async def flush_for(self, event_id: str, *, timeout: float = 5.0) -> None:
        """同步等指定 ``event_id`` 落盘。

        - 已在 ``written_event_ids`` 内 → 立即返回。
        - 否则注册 ``asyncio.Event`` 等 :meth:`on_session_event` / :meth:`__call__`
          通知;超时抛 :class:`PersistenceFlushTimeout`。

        Args:
            event_id: EnvelopeRef.event_id。
            timeout: 最长等待秒数,默认 5s。
        """
        if event_id in self._written_event_ids:
            return
        event = self._flush_events.get(event_id)
        if event is None:
            event = asyncio.Event()
            self._flush_events[event_id] = event
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise PersistenceFlushTimeout(event_id, timeout) from exc

    async def flush(self, *, timeout: float = 30.0) -> None:
        """强制 sink fsync(lifespan shutdown / 测试用)。

        无队列可 drain;仅推盘 buffer。``timeout`` 保留签名兼容,未使用。
        """
        _ = timeout
        self._sink.flush()
        self._last_flush_ms = int(time.time() * 1000)

    def _maybe_fsync_batched(self) -> None:
        """BATCH 策略:间隔 fsync_interval_ms 触发一次 fsync;计入 last_flush_ms。"""
        last = self._last_flush_ms
        now_ms = int(time.time() * 1000)
        if last is None or (now_ms - last) >= self._fsync_interval_ms:
            self._sink.flush()
            self._last_flush_ms = now_ms

    def _persist_record(self, record: SpineEventRecord, event_id: str) -> None:
        """写一条 record 到 sink;失败 contained。

        成功则更新 written 计数、按 fsync_policy flush、通知 flush_for。
        Session.observe 与 EnvelopeDeliveryObserver 共用本入口。
        """
        try:
            self._sink.append(record)
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
            self._sink.flush()
            self._last_flush_ms = int(time.time() * 1000)
        elif self._fsync_policy is FsyncProtocol.BATCH and self._fsync_interval_ms > 0:
            self._maybe_fsync_batched()
        # COMMIT:运行期不 fsync,落盘时机由 sink.close() 决定。
        self._notify_flush(event_id)

    def _notify_flush(self, event_id: str) -> None:
        """通知 ``flush_for`` 等待方(写入尝试结束,成功或 contained 失败)。"""
        event: asyncio.Event | None = self._flush_events.pop(event_id, None)
        if event is not None:
            event.set()

    @staticmethod
    def _build_persistable_record(payload: EventPayload, ref: EnvelopeRef) -> SpineEventRecord:
        from lca_kernel.events.spine_runtime import build_record

        return build_record(payload, ref)

    def __repr__(self) -> str:
        return (
            f"PersistenceObserver(policy={self._fsync_policy.value!r}, "
            f"written_total={self._written_total})"
        )


__all__ = [
    "EnvelopeDeliveryObserver",
    "PersistenceFlushTimeout",
    "PersistenceHealthSnapshot",
    "PersistenceObserver",
]
