"""PersistenceObserver —— ADR-0186 PR-3e 落盘 observer。

唯一 :class:`lca_kernel.events.sinks.SinkBackend`(<run_id>.spine.jsonl)
异步消费者:后台 :class:`asyncio.Task` 拉 :class:`lca_kernel.events.queue.DeliveryQueue`
逐 envelope 调 :func:`lca_kernel.events.spine_runtime.build_record` + ``backend.append``,
fsync 策略可配。

PR-3e(对齐 DSH ``JsonlSessionPersistence``):observer 形态,两条入口共享同一 sink。
- 实现 :class:`lca_kernel.events.session.SessionObserver` (``__call__(session, event)``):
  可直接 ``Session.observe(observer)``。SessionEvent 映射为 payload/ref 后写
  同一 sink(保留 ``trace_id``)。
- 实现 :class:`EnvelopeDeliveryObserver` (``on_session_event(payload, ref)``)。
- 后台 consumer 路径保留,仍走 ``queue.aiter`` + ``on_session_event``(内
  部等价),便于 :class:`EventBus.publish_async` 的强一致 flush_for 复用。
- 失败 ``contained``:单条 envelope 落盘失败 / build_record / SessionEvent 映射
  失败仅记日志 + ``mark_drained``,不杀 consumer loop、不上抛 Session.append
  (与 DSH 一致)。

责任边界:
- 唯一 ``seq/epoch/hash`` 分配链消费者(经 :mod:`lca.infrastructure.observability.spine.context`
  已在 :mod:`lca_kernel.events.spine_runtime.build_record` 注入,observer 不直接分配)。
- 唯一 ``<run_id>.spine.jsonl`` 物理写入入口——前提是 caller 把同一个
  :class:`lca_kernel.events.queue.DeliveryQueue` 传给 observer(**单实例 SSOT**)。
  :class:`lca_kernel.events.bus.EventBus.publish` 默认与 :meth:`PersistenceObserver.default`
  不共享 queue;因此 sync :meth:`EventBus.publish` 仍走 ``_dispatch_sinks`` 同步落盘
  兼容路径(wire 兼容),async :meth:`EventBus.publish_async` 走 observer 落盘(强一致)。

设计要点:
- 后台 consumer task 在 :meth:`start` 时创建,持续 ``aiter`` 直到 :meth:`stop` 取消。
- ``flush_for(event_id)`` 用于 caller 同步等指定 envelope 落盘;内部用
  ``asyncio.Event`` per event 通知,避免 busy poll。
- ``fsync_policy``:SYNC(每事件 fsync)/ BATCH(50ms 间隔)/ ASYNC(后台线程 fsync)。
  SYNC/BATCH 在 consume loop 内 inline 调用 ``backend.flush``;ASYNC 留给上层 Profile 接入。
- ``PersistenceHealthSnapshot`` 暴露给 ``/health`` + ``lca-ops events-delivery --policy``。

COMPAT(delete-when: 2026-10-04 后无人引用 PersistenceWorker 符号,
       tracking: ADR-0186 PR-3e):
:class:`PersistenceWorker` 是 :class:`PersistenceObserver` 的别名,保留 30 天
以兼容 PR-2 引入期间已发布的内部引用(bus / event_spine / webserver handler / CLI)。
"""

from __future__ import annotations

import asyncio
import contextlib
import enum
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

if TYPE_CHECKING:
    from lca.contracts.event import EventPayload
    from lca_kernel.events.bus import EnvelopeRef
    from lca_kernel.events.queue import DeliveryQueue
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

    设计意图:与 DSH ``JsonlSessionPersistence.onEvent()`` 形态一致,
    让 SessionBus 之类组件无须关心 observer 内部后台 task/queue。
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
        execution_point = "unknown"
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


class FsyncPolicy(enum.Enum):
    """fsync 策略枚举(ADR-0184 PR-2)。"""

    SYNC = "sync"
    """每事件 fsync(强一致,低吞吐)。"""

    BATCH = "batch"
    """默认。``fsync_interval_ms`` 间隔或 ``fsync_batch_size`` 累积到阈值时 fsync。
    本 observer 默认 50ms 间隔;批次大小由底层 :class:`lca_kernel.events.sinks.spine_sink.SpineSink`
    自身 ``fsync_batch_size`` 控制(默认 100)。
    """

    ASYNC = "async"
    """后台线程 fsync(高吞吐,弱一致)。本 observer 不实装线程,默认与 BATCH 等效;
    Profile 加载时可挂自定义 SinkBackend 实现真正的 ASYNC 路径。"""


class PersistenceFlushTimeout(TimeoutError):
    """``flush_for`` 在指定超时内未等到 envelope 落盘。

    单点错误面:caller 接 :class:`TimeoutError` 时区分本类,便于 caller 决定
    是 retry 还是 fail-loud。事件可能已落盘或仍留在 queue(consumer 慢)。
    """

    def __init__(self, event_id: str, timeout_s: float) -> None:
        super().__init__(f"PersistenceObserver.flush_for({event_id!r}) 在 {timeout_s}s 内未落盘")
        self.event_id = event_id
        self.timeout_s = timeout_s


@dataclass(frozen=True, slots=True)
class PersistenceHealthSnapshot:
    """observer 健康快照,供 ``/health`` + ``lca-ops events-delivery --policy`` 投影。"""

    policy: FsyncPolicy
    queue_depth: int
    pending_count: int
    last_flush_ms: int | None
    enqueued_total: int
    dropped_queue_full: int
    written_total: int
    consumer_running: bool


# ── 主类 ──────────────────────────────────────────────────────────────────


class PersistenceObserver:
    """SessionObserver + EnvelopeDeliveryObserver + 后台 consumer(PR-3e)。

    实现 :class:`SessionObserver`:``Session.observe(observer)`` 在 append 提交后
    调 :meth:`__call__`,内部映射 SessionEvent → payload/ref 再走
    :meth:`on_session_event`。
    实现 :class:`EnvelopeDeliveryObserver`:外部(SyncEventBus / SessionBus 等)
    可直接调 :meth:`on_session_event`。
    后台 ``_consume_loop`` 内部也走 :meth:`on_session_event`(统一 sink 写入
    入口),保证三条路径(Session.observe / 直接 observer 回调 / queue 异步消费)
    共享同一 fsync 策略 + 计数器。

    进程级单例(:meth:`default`);与 :class:`lca_kernel.events.bus.EventBus.default`
    的 DeliveryQueue **解耦**——sync :meth:`EventBus.publish` 仍走
    ``_dispatch_sinks`` 同步落盘,async :meth:`EventBus.publish_async` 走
    observer 异步落盘。两者不共享 sink 时不冲突。
    """

    _default_instance: ClassVar[PersistenceObserver | None] = None

    def __init__(
        self,
        *,
        sink: SinkBackend | None = None,
        queue: DeliveryQueue | None = None,
        fsync_policy: FsyncPolicy = FsyncPolicy.BATCH,
        fsync_interval_ms: int = 50,
    ) -> None:
        from lca_kernel.events.queue import DeliveryQueue
        from lca_kernel.events.sinks.spine_sink import SpineSink

        self._sink: SinkBackend = sink if sink is not None else SpineSink()
        self._queue: DeliveryQueue = queue if queue is not None else DeliveryQueue()
        self._fsync_policy = fsync_policy
        self._fsync_interval_ms = fsync_interval_ms
        self._consumer_task: asyncio.Task[None] | None = None
        self._written_event_ids: set[str] = set()
        self._written_total = 0
        self._last_flush_ms: int | None = None
        self._flush_events: dict[str, asyncio.Event] = {}
        self._idle_event: asyncio.Event = asyncio.Event()
        self._idle_event.set()  # queue 初始为空,允许 flush() 立即通过
        # ``_written_event_ids`` 集合读多写少且修改都是原子(``add`` /
        # ``in`` 是 GIL 临界区),无需显式锁。``_flush_events`` dict 的
        # ``get`` / ``pop`` 在 :meth:`flush_for` 与 :meth:`_notify_flush`
        # 之间没有跨事件循环的并发写,亦无需 ``asyncio.Lock``。
        self._lock: asyncio.Lock | None = None  # 保留位,目前未使用
        self._stopping = False

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
        drain + 通知 flush_for 等待方;不向外冒泡,observer 自身不进入
        不可用状态。

        注:``on_session_event`` 是 sync 接口(对齐 DSH ``onEvent`` 形态),
        ``build_record`` / ``sink.append`` 均为同步调用;后台 consumer 协
        程从 :meth:`_consume_loop` 调到此方法时不需要 await。

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
        """进程级默认实例。多次调用返回同一对象。

        ADR-0186 PR-3b 后 ``EnvelopeBus`` 不再持有 ``DeliveryQueue``；
        默认实例自建内部队列（仅服务仍走 ``on_session_event`` / flush 的路径）。
        Session.observe 主写路径不依赖本单例与 bus 共享队列。
        """
        if cls._default_instance is None:
            cls._default_instance = cls()
        return cls._default_instance

    @classmethod
    def set_default(cls, instance: PersistenceObserver | None) -> None:
        cls._default_instance = instance

    @classmethod
    def reset_singleton(cls) -> None:
        """测试隔离:清空默认实例。下次 :meth:`default` 重新构造。

        注:**不**等 consumer task 退出——若测试 fixture 需要先停止
        consumer,显式 await :meth:`stop`。
        """
        cls._default_instance = None

    @classmethod
    async def stop_default_if_running(cls) -> None:
        """测试隔离 helper:仅当 :meth:`default` 存在实例 + consumer 运行中,
        await 停止 consumer;否则 no-op。fixture 链中出错不会因为僵尸
        consumer task 阻塞事件循环。

        必须在 ``event loop`` 内调用(async 上下文);不能跨 fixture 直接
        调 :meth:`reset_singleton`,因为 consumer task 还可能被 await 阻塞。
        """
        if cls._default_instance is None:
            return
        inst = cls._default_instance
        task = inst._consumer_task
        if task is None or task.done():
            return
        inst._stopping = True
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, RuntimeError):
            await task

    # ── 只读属性 ─────────────────────────────────────────────────────────

    @property
    def fsync_policy(self) -> FsyncPolicy:
        return self._fsync_policy

    @property
    def fsync_interval_ms(self) -> int:
        return self._fsync_interval_ms

    @property
    def sink(self) -> SinkBackend:
        return self._sink

    @property
    def queue(self) -> DeliveryQueue:
        return self._queue

    @property
    def pending_count(self) -> int:
        """当前 queue 内未消费的 envelope 数。"""
        return self._queue.depth

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
        return self._consumer_task is not None and not self._consumer_task.done()

    def health_snapshot(self) -> PersistenceHealthSnapshot:
        return PersistenceHealthSnapshot(
            policy=self._fsync_policy,
            queue_depth=self._queue.depth,
            pending_count=self.pending_count,
            last_flush_ms=self._last_flush_ms,
            enqueued_total=self._queue.enqueued_total,
            dropped_queue_full=self._queue.dropped_queue_full,
            written_total=self._written_total,
            consumer_running=self.consumer_running,
        )

    # ── 生命周期 ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """启动后台 consumer task(幂等)。"""
        if self._consumer_task is not None and not self._consumer_task.done():
            return
        self._stopping = False
        self._consumer_task = asyncio.create_task(self._consume_loop(), name="persistence-observer")

    async def stop(self) -> None:
        """取消后台 consumer task 并 await 退出。"""
        self._stopping = True
        task = self._consumer_task
        if task is None or task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    # ── 同步等接口 ───────────────────────────────────────────────────────

    async def flush_for(self, event_id: str, *, timeout: float = 5.0) -> None:
        """同步等指定 ``event_id`` 落盘并 fsync。

        - 若 consumer 未启动则惰性启之(:meth:`start`)。
        - 已在 ``written_event_ids`` 内 → 立即返回(已落盘)。
        - 否则注册 ``asyncio.Event`` 等 consumer 通知;超时抛
          :class:`PersistenceFlushTimeout`。

        Args:
            event_id: EnvelopeRef.event_id。
            timeout: 最长等待秒数,默认 5s。生产端强一致路径可调高。
        """
        await self.start()
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
        """flush 所有 pending envelope(lifespan shutdown / 测试用)。

        启动 consumer 后等 ``queue.depth == 0``;最后做一次 fsync 把
        buffer 余量推盘。超时抛 :class:`PersistenceFlushTimeout`。

        实现:用 :class:`asyncio.Event` 与后台 consumer 协同 —— consumer
        在 ``mark_drained`` 后若 ``queue.depth == 0`` 设 ``_idle_event``。
        避免 sleep-poll(ruff ASYNC110)。
        """
        await self.start()
        deadline = time.monotonic() + timeout
        # 清 idle 标志:接下来 consumer 至少需要 mark_drained 到 depth=0 才 set 它。
        self._idle_event.clear()
        while self._queue.depth > 0 and time.monotonic() < deadline:
            try:
                await asyncio.wait_for(
                    self._idle_event.wait(),
                    timeout=max(0.001, deadline - time.monotonic()),
                )
            except asyncio.TimeoutError:
                continue
            self._idle_event.clear()
        if self._queue.depth > 0:
            raise PersistenceFlushTimeout("<all-pending>", timeout)
        # 已 drain:留 idle_event set 状态,下次 flush() 入口直接通过第一段 while。
        self._idle_event.set()
        self._sink.flush()
        self._last_flush_ms = int(time.time() * 1000)

    # ── 后台 consumer loop ─────────────────────────────────────────────

    async def _consume_loop(self) -> None:
        """后台 task:持续从 queue 拉 envelope → 走 :meth:`on_session_event`。

        错误语义(FD-1, ADR-0184):queue.aiter 内部异常日志吞错,循环不退出;
        单条 envelope 处理失败由 :meth:`on_session_event` 自包含(contained),
        不杀整个 observer。
        """
        while not self._stopping:
            try:
                ref, payload = await self._queue.aiter().__anext__()
            except StopAsyncIteration:
                break
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("persistence observer aiter failed")
                continue
            self.on_session_event(payload, ref)
            self._queue.mark_drained(ref.event_id)
            # 通知 flush() 等候方:队列空了就 set idle_event。
            if self._queue.depth == 0:
                self._idle_event.set()

    def _maybe_fsync_batched(self) -> None:
        """BATCH 策略:间隔 fsync_interval_ms 触发一次 fsync;计入 last_flush_ms。"""
        if self._sink is None:
            return
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
        if self._fsync_policy is FsyncPolicy.SYNC:
            self._sink.flush()
            self._last_flush_ms = int(time.time() * 1000)
        elif self._fsync_policy is FsyncPolicy.BATCH and self._fsync_interval_ms > 0:
            self._maybe_fsync_batched()
        self._notify_flush(event_id)

    def _notify_flush(self, event_id: str) -> None:
        """通知 ``flush_for`` 等待方。事件未必"成功 fsync"(只是离开 queue)。"""
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
            f"queue_depth={self._queue.depth}, written_total={self._written_total}, "
            f"consumer_running={self.consumer_running})"
        )


# COMPAT(delete-when: 2026-10-04 后无人引用 PersistenceWorker 符号,
#        tracking: ADR-0186 PR-3e):PR-2 引入期已发布的内部引用
#        (lca_kernel.events.bus.publish_async / lca.infrastructure.observability
#        .spine.event_spine.append_async / lca.infrastructure.cli.commands
#        .events_delivery / webserver handler query_endpoints)在 PR-3e 收口前
#        已锁定为 PersistenceWorker 字面量;为避免一次性大范围 churn 触发
#        回归,保留同名字符串别名 30 天,后续 PR-3e-followup 逐文件迁移。
PersistenceWorker = (
    PersistenceObserver  # COMPAT(delete-when: 2026-10-04 后无人引用, tracking: ADR-0186 PR-3e)
)


__all__ = [
    "EnvelopeDeliveryObserver",
    "FsyncPolicy",
    "PersistenceFlushTimeout",
    "PersistenceHealthSnapshot",
    "PersistenceObserver",
    "PersistenceWorker",  # COMPAT: 30 天窗口,见上方别名说明
]
