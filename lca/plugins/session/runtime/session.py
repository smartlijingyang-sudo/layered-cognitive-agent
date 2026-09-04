"""Session 实体 —— DSH 风格 append-only session 真值（PR-3c 骨架）。

对齐 deepseek-harness ``packages/core/session/src/index.ts`` ``Session.append``
的核心语义链：**校验 → 入日志 → fire observers（contained）→ 返回事件**。
骨架不含 surface 机制、fork/seed、persistence —— 那些由后续 PR 在此实体上叠加。

与 dsh 的显式差异：

- observer 注册走 :meth:`Session.observe`（per-session），不依赖 cordis
  ``session/event`` 全局派发；store 层装配观察者由后续 PR 接管。
- 事件词表开放：``type`` 即 spine category 字符串，无 close-set 校验
  （新 category 走 yaml 注册，ADR-0183）。
"""

from __future__ import annotations

import contextlib
import json
import time
from collections.abc import Callable, Mapping
from typing import Any

import structlog

from lca_kernel.events.fold import EpochHeader, foldRequestHeader
from lca_kernel.events.session import (
    SESSION_FORMAT_VERSION,
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


def _snapshot_data(data: Mapping[str, Any]) -> dict[str, Any]:
    """无损 JSON 快照：校验可序列化性并与调用方可变输入脱钩。

    对齐 dsh ``snapshotJsonValue``：校验与拷贝走同一遍序列化，日志里落的
    是快照值，不是调用方引用的对象。``allow_nan=False`` 拒绝非 JSON 数值。
    """
    if not isinstance(data, Mapping):
        raise TypeError(f"session event data 必须是 Mapping, got {type(data).__name__}")
    try:
        encoded = json.dumps(data, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"session event data 不是可无损 JSON 序列化的值: {exc}") from exc
    snapshot = json.loads(encoded)
    if not isinstance(snapshot, dict):
        raise TypeError(
            f"session event data 序列化后必须是 JSON object, got {type(snapshot).__name__}"
        )
    return snapshot


class Session(SessionProtocol):
    """事件溯源 Session：append-only 日志是唯一真值，投影从日志派生。

    时序契约（对齐 dsh ``Session.append``）：

    1. ``append`` 入口先校验（type 非空 + data 无损 JSON 快照），失败时日志不变；
    2. 校验通过后检测重入标记，抛 :class:`SessionReentryError` 时日志不变；
    3. 置重入标记 → observer 快照 → 事件入日志 → 失效快照缓存 →
       逐个 fire observer（单个失败 contained，不打断后续）→ 返回事件；
    4. ``finally`` 清重入标记，保证失败路径也恢复可 append 状态。
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
        self._appending = False
        self._events_snapshot: tuple[SessionEvent, ...] | None = None
        self._header_fold: EpochHeader | None = None
        self._header_fold_seq = 0

    @property
    def event_count(self) -> int:
        """当前 in-memory log 长度(= next seq)。"""
        return len(self._log)

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

    def append(self, event_type: str, data: Mapping[str, Any]) -> SessionEvent:
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
        event = SessionEvent(type=event_type, seq=len(self._log), time=_now_ms(), data=snapshot)
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
