"""Session append public API (ADR-0195 P1-03).

Production fact append goes through :class:`Session` and its :meth:`~Session.append`.
"""

from __future__ import annotations

import contextlib
import copy
import inspect
import math
import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from typing import Any

import structlog
from pydantic import BaseModel

from lca_kernel.events.fold.fold import EpochHeader, foldRequestHeader
from lca_kernel.events.session.session import (
    SESSION_FORMAT_VERSION,
    FlushListener,
    FlushResult,
    SessionEvent,
    SessionHeader,
    SessionObserver,
    SessionProtocol,
    SessionReentryError,
)

_log = structlog.get_logger(__name__)

__all__ = ["Session"]


def _now_ms() -> int:
    """append / 创建时刻的 Unix epoch 毫秒（对齐 dsh ``Date.now()``）。"""
    return int(time.time() * 1000)


def _to_jsonable(value: Any) -> Any:
    """Lift Pydantic/dataclass/Sequence/primitive values into JSON-safe primitives.

    The fact-plane boundary owns typed-container conversion: callers can hand
    over ``ContextManifest``-shaped dataclasses or Pydantic models nested in a
    Mapping without manually calling ``asdict``. Anything this converter does
    not recognize stays a ``TypeError`` so silent loss of structure can't
    sneak through.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, BaseModel):
        return _to_jsonable(value.model_dump(mode="python"))
    if is_dataclass(value) and not isinstance(value, type):
        return _to_jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)) or (
        isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
    ):
        return [_to_jsonable(v) for v in value]
    raise TypeError(f"session event data 包含不可无损 JSON 序列化的值: {type(value).__name__}")


# 单 event payload hard cap(以 _to_jsonable 之后的 JSON 字节数估算)。
# 超过即 fail-loud,避免一次同步 emit 把 asyncio 事件循环独占数秒
# (per 2026-09-16 stall postmortem)。环境变量可覆盖,默认 8 MiB。
_MAX_SNAPSHOT_BYTES = int(os.environ.get("LCA_SESSION_MAX_SNAPSHOT_BYTES", str(8 * 1024 * 1024)))


def _estimate_size(value: Any) -> int:
    """估算 JSON 序列化后字节数,不分配中间字符串。

    仅用于大小守卫,粗估足够(int/float 按 token 字节、str 按 len+2、
    dict/list 按递归成员+1 边界)。复杂度 O(N) 与 deepcopy 同阶。
    """
    if value is None or isinstance(value, bool):
        return 4 if value is None else (4 if value else 5)
    if isinstance(value, int):
        return max(1, len(str(value)))
    if isinstance(value, float):
        return 24  # 浮点最长 token
    if isinstance(value, str):
        # 中文 / surrogate 大约 4 字节,UTF-8 编码,粗估 2 倍 + 引号
        return len(value.encode("utf-8", errors="replace")) * 2 + 2
    if isinstance(value, dict):
        return 2 + sum(_estimate_size(k) + _estimate_size(v) for k, v in value.items())
    if isinstance(value, list):
        return 2 + sum(_estimate_size(v) for v in value)
    return 16  # 兜底,_to_jsonable 已保证走到这里只有 dict/list/primitive


def _validate_json_safe(value: Any) -> None:
    """递归校验 lifted 树无 NaN/Infinity,不构造中间字符串。

    比 ``json.dumps(..., allow_nan=False)`` 快一个数量级,且不分配大字符串。
    失败语义与原实现一致:抛 ``ValueError`` -> ``TypeError``。
    """
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"非 JSON 数值: {value!r}")
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise ValueError(f"JSON object key 必须是 str, got {type(k).__name__}")
            _validate_json_safe(v)
        return
    if isinstance(value, list):
        for v in value:
            _validate_json_safe(v)
        return
    # primitive (None/bool/int/str) 经 _to_jsonable 已保证 JSON-safe


def _snapshot_data(data: Mapping[str, Any]) -> dict[str, Any]:
    """无损 JSON 快照:校验可序列化性并与调用方可变输入脱钩。

    实现路径(2026-09-16 重构):

    1. :func:`_to_jsonable` 在边界处把 ``BaseModel`` / dataclass /
       Sequence 提升为 ``dict`` / ``list`` / 原语(JSON-safe 原语集合);
    2. :func:`_validate_json_safe` 递归扫 NaN/Infinity,替代原先的
       ``json.dumps(allow_nan=False)`` —— 后者在 100MB+ payload 上会
       分配大字符串并扫一遍,本实现在 lifted 树上直接递归,常数因子小;
    3. :func:`copy.deepcopy` 做深拷贝 + memo,替代原先 ``json.loads(encoded)``。
       deepcopy 不做"stringify→parse"往返,且保留 ``_to_jsonable`` 已经
       归一化好的 ``dict``/``list`` 容器 + 共享引用(原 json.loads 会丢
       共享引用)。

    ``_MAX_SNAPSHOT_BYTES``(默认 8 MiB)做 hard cap:任何单 event payload
    超过阈值即抛 ``TypeError``。这是事件循环 backpressure 的最后一公里
    —— 单 event 不可能因为 log size 增长而把 asyncio 独占数秒。环境变量
    ``LCA_SESSION_MAX_SNAPSHOT_BYTES`` 可覆盖。

    对齐 dsh ``snapshotJsonValue`` 的**语义**(独立快照 + JSON-safe),非
    字符级输出对齐;``Session.append`` 同步契约不变(ADR-0186)。
    """
    if not isinstance(data, Mapping):
        raise TypeError(f"session event data 必须是 Mapping, got {type(data).__name__}")
    lifted = _to_jsonable(data)
    size = _estimate_size(lifted)
    if size > _MAX_SNAPSHOT_BYTES:
        raise TypeError(
            f"session event payload 超过 _MAX_SNAPSHOT_BYTES={_MAX_SNAPSHOT_BYTES} "
            f"(估算 {size} bytes);降低单 event payload 大小或调高 "
            f"LCA_SESSION_MAX_SNAPSHOT_BYTES。"
        )
    try:
        _validate_json_safe(lifted)
    except ValueError as exc:
        raise TypeError(f"session event data 不是可无损 JSON 序列化的值: {exc}") from exc
    return copy.deepcopy(lifted)


class Session(SessionProtocol):
    """事件溯源 Session：append-only 日志是唯一真值，投影从日志派生。

    时序契约（对齐 dsh ``Session.append``）：

    1. ``append`` 入口先校验（type 非空 + data 无损 JSON 快照），失败时日志不变；
    2. 校验通过后检测重入标记，抛 :class:`SessionReentryError` 时日志不变；
    3. 置重入标记 → observer 快照 → 事件入日志 → 失效快照缓存 →
       逐个 fire observer（单个失败 contained，不打断后续）→ 返回事件；
    4. ``finally`` 清重入标记，保证失败路径也恢复可 append 状态。

    flush 链（ADR-0186）：

    1. 取当前 listener + observer 快照；
    2. 依次 await ``listener.flush(session)``，失败 contained 记 ``FlushResult(ok=False)``；
    3. 对每个 observer 探测 ``getattr(observer, 'flush', None)`` 并 await，同样 contained。
    """

    def __init__(self, session_id: str, header: SessionHeader | None = None) -> None:
        """构造 detached session；``header`` 缺省时合成最小 header。

        precondition：``session_id`` 非空；显式 ``header`` 的 ``id`` /
        ``version`` 必须与 ``session_id`` / :data:`SESSION_FORMAT_VERSION` 一致。
        失败语义：违反抛 ``ValueError``。
        """
        if not isinstance(session_id, str) or not session_id:
            raise ValueError(f"session_id 必须是非空字符串, got {session_id!r}")
        if header is None:
            header = SessionHeader(
                version=SESSION_FORMAT_VERSION,
                id=session_id,
                created_at=_now_ms(),
            )
        if header.id != session_id:
            raise ValueError(f"header.id {header.id!r} 与 session_id {session_id!r} 不一致")
        if header.version != SESSION_FORMAT_VERSION:
            raise ValueError(
                f"header.version 必须是 {SESSION_FORMAT_VERSION}, got {header.version}"
            )
        self._header = header
        self._log: list[SessionEvent] = []
        self._observers: list[SessionObserver] = []
        self._flush_listeners: list[FlushListener] = []
        self._appending = False
        self._events_snapshot: tuple[SessionEvent, ...] | None = None
        self._header_fold: EpochHeader | None = None
        self._header_fold_seq = 0
        self._projections: Any | None = None

    @property
    def event_count(self) -> int:
        """当前 in-memory log 长度(= next seq)。"""
        return len(self._log)

    @property
    def flush_listener_count(self) -> int:
        """当前注册的显式 flush listener 数量（不含 observer-duck-typed flush）。"""
        return len(self._flush_listeners)

    @property
    def header(self) -> SessionHeader:
        """创建时盖章的不可变存储元数据。"""
        return self._header

    @property
    def id(self) -> str:
        """session 唯一标识，派生自 ``header.id`` 的单份真值。"""
        return self._header.id

    @property
    def seq(self) -> int:
        """下一条事件的序号 —— 恒等于当前日志长度（``seq = len(log)`` 契约）。"""
        return len(self._log)

    def append(
        self,
        event_type: str,
        data: Mapping[str, Any],
        *,
        actor: str | None = None,
        visibility: str = "model",
        ignorable: bool = False,
        surface_op: Any | None = None,
        source_event_seqs: tuple[int, ...] | None = None,
    ) -> SessionEvent:
        """校验 → 入日志 → fire observers（contained）→ 返回落日志的事件。

        precondition：``event_type`` 非空字符串；``data`` 可无损 JSON 序列化。
        失败语义：校验不过抛 ``TypeError`` / ``ValueError``；observer fire
        期间重入抛 :class:`SessionReentryError` —— 两种失败都不改日志。
        时序：事件入日志先于 observer fire，observer 读到的是已提交状态。
        所有权：返回事件的 ``data`` 是快照，调用方后续改输入不影响日志。
        """
        if not isinstance(event_type, str) or not event_type:
            raise ValueError(f"session event type 必须是非空字符串, got {event_type!r}")
        snapshot = _snapshot_data(data)
        if self._appending:
            raise SessionReentryError(
                f"session {self.id!r} append 重入: 上一次 append 的 observer fire 未结束"
            )
        event = SessionEvent(
            type=event_type,
            seq=len(self._log),
            time=_now_ms(),
            data=snapshot,
            session_id=self.id,
            actor=actor,
            visibility=visibility,  # type: ignore[arg-type]
            ignorable=ignorable,
            surface_op=surface_op,
            source_event_seqs=source_event_seqs,
        )
        self._appending = True
        try:
            # observer 快照在入日志前取：fire 期间新注册的观察者不收本事件。
            observers = tuple(self._observers)
            self._log.append(event)
            self._events_snapshot = None
            for observer in observers:
                try:
                    observer(self, event)
                except Exception:  # containment boundary: 单个 observer 失败不打断提交链
                    _log.warning(
                        "session.observer.failed",
                        session_id=self.id,
                        seq=event.seq,
                        event_type=event.type,
                        exc_info=True,
                    )
            return event
        finally:
            self._appending = False

    async def flush(self) -> list[FlushResult]:
        """await 全部 durability listener + observer-duck-typed flush（contained）。

        顺序：先跑 ``_flush_listeners``，再对每个 ``_observers`` 探测 duck-type
        ``flush`` 方法。单个 listener 抛错被 contained（记 ``FlushResult.ok=False`` +
        结构化日志），不打断其余 listener。返回结果按调用顺序排列。
        """
        results: list[FlushResult] = []
        event_count = len(self._log)

        # 快照后遍历：flush 期间新注册的 listener 不收本次调用。
        for listener in tuple(self._flush_listeners):
            results.append(await self._invoke_flush_listener(listener, event_count))

        for observer in tuple(self._observers):
            flush_fn = getattr(observer, "flush", None)
            if flush_fn is None or not callable(flush_fn):
                continue
            try:
                maybe_coro = flush_fn(self)
                # duck-type observer.flush 若是 async，await 它；同步则直接忽略返回值。
                if inspect.isawaitable(maybe_coro):
                    await maybe_coro
                results.append(
                    FlushResult(
                        listener=observer,  # type: ignore[arg-type]
                        ok=True,
                        event_count=event_count,
                    )
                )
            except Exception as exc:
                _log.warning(
                    "session.observer_flush.failed",
                    session_id=self.id,
                    event_count=event_count,
                    exc_info=True,
                )
                results.append(
                    FlushResult(
                        listener=observer,  # type: ignore[arg-type]
                        ok=False,
                        event_count=event_count,
                        error=exc,
                    )
                )

        return results

    async def _invoke_flush_listener(
        self, listener: FlushListener, event_count: int
    ) -> FlushResult:
        """await 单个显式 flush listener，失败 contained 并记录结构化日志。"""
        try:
            await listener.flush(self)
            return FlushResult(listener=listener, ok=True, event_count=event_count)
        except Exception as exc:
            _log.warning(
                "session.flush_listener.failed",
                session_id=self.id,
                event_count=event_count,
                exc_info=True,
            )
            return FlushResult(listener=listener, ok=False, event_count=event_count, error=exc)

    def register_flush_listener(self, listener: FlushListener) -> Callable[[], None]:
        """注册显式 flush durability listener；返回幂等取消函数。

        时序：只对后续 ``flush()`` 调用生效；取消后下次 flush 不再调用该
        listener；幂等取消：重复取消静默通过。
        """
        self._flush_listeners.append(listener)

        def cancel() -> None:
            with contextlib.suppress(ValueError):
                self._flush_listeners.remove(listener)

        return cancel

    def snapshot_events(
        self, from_seq: int = 0, to_seq_exclusive: int | None = None
    ) -> tuple[SessionEvent, ...]:
        """半开区间 ``[from_seq, to_seq_exclusive)`` 的不可变事件快照。

        失败语义：区间越界（负值 / 超日志尾 / 反向）抛 ``ValueError``。
        全量快照缓存到下次 append；区间快照每次返回新 tuple。事件对象本身
        frozen，快照与后续 append 互不影响。
        """
        end = len(self._log) if to_seq_exclusive is None else to_seq_exclusive
        if from_seq < 0 or end < from_seq or end > len(self._log):
            raise ValueError(f"snapshot 区间 [{from_seq}, {end}) 越界 (日志长度 {len(self._log)})")
        if from_seq == 0 and end == len(self._log):
            if self._events_snapshot is None:
                self._events_snapshot = tuple(self._log)
            return self._events_snapshot
        return tuple(self._log[from_seq:end])

    def event_at(self, seq: int) -> SessionEvent | None:
        """按精确序号取事件；不存在返回 ``None``（不抛）。"""
        if 0 <= seq < len(self._log):
            return self._log[seq]
        return None

    def request_header(self) -> EpochHeader | None:
        """最后一条 header 事件生效后的 :class:`EpochHeader`；无 header 返回 ``None``。

        增量 fold：只扫上次读后新增的事件，每条 header 事件只被 fold 一次；
        无新事件时直接返回缓存。与 ``foldRequestHeader(snapshot_events())``
        全量形态结果一致（:func:`lca_kernel.events.fold.foldRequestHeader`
        的 ``from_`` 续接语义）。
        """
        if self._header_fold_seq < len(self._log):
            self._header_fold = foldRequestHeader(
                self._log[self._header_fold_seq :], from_=self._header_fold
            )
            self._header_fold_seq = len(self._log)
        return self._header_fold

    def _attach_projection_registry(self, registry: Any) -> None:
        """Wire projection registry for incremental model-visible reads (ADR-0193)."""
        self._projections = registry

    def derive_messages(self) -> list[dict[str, Any]]:
        """Model-visible messages via projection fabric, else pure fold replay."""
        from lca.plugins.session.runtime.projection.reader import model_visible_messages

        return model_visible_messages(self, registry=self._projections)

    def observe(self, observer: SessionObserver) -> Callable[[], None]:
        """注册 append 观察者；返回幂等取消函数。

        时序：注册只对**后续** append 生效；fire 期间注册不影响进行中的派发
        （观察者快照先于入日志取得）。
        """
        self._observers.append(observer)

        def cancel() -> None:
            # 幂等：重复取消静默通过
            with contextlib.suppress(ValueError):
                self._observers.remove(observer)

        return cancel

    def __repr__(self) -> str:
        return f"Session(id={self.id!r}, seq={self.seq})"
