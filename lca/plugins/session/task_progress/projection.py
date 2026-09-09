"""TaskProgressProjection — 观察面 fold(ADR-0214 §4.2)。

从 Session events 折叠出当前 ``TaskProgress`` + ``confidence_history``:

- 只读 Session, 不反向写事实 (C4 兑现)
- fold 幂等: 同一组 events fold 两次结果一致 (C9 兑现)
- completed 单调 (新 completed ⊇ 旧 completed; sorted+set 合并稳定)
- confidence 历史长度 ≤ ``HISTORY_MAXLEN = 10``

API 与 :class:`TurnControlUnit` 同形(``init`` / ``apply`` / ``view`` /
``fold``),便于共用 fold harness / 测试 fixture。
"""

from __future__ import annotations

from collections import deque
from typing import Any, cast

from lca.contracts.harness.memory.events import TaskProgressCommitted
from lca.contracts.models.core.execution.task_progress import TaskProgress
from lca_kernel.events.session.session import SessionEvent

__all__ = ["HISTORY_MAXLEN", "TaskProgressProjection"]

HISTORY_MAXLEN: int = 10
_TASK_PROGRESS_COMMIT = "task_progress.commit.v1"


class TaskProgressProjection:
    """观察面 fold: Session events → 当前 task_progress 状态 + 历史。

    ADR-0214 §4.2 SSOT。
    """

    key = "task_progress"
    state_version = 1

    def __init__(self) -> None:
        self._state: TaskProgress | None = None
        self._confidence_history: deque[float] = deque(maxlen=HISTORY_MAXLEN)
        # PR-B: per-snapshot completed set, 用于 PR-B MultiToolLoopBreakerGate
        # 的 "completed flatline" 触发判定。maxlen 与 confidence 一致,
        # 与 `is_stuck(window)` 的窗口语义对齐。
        self._completed_history: deque[tuple[str, ...]] = deque(maxlen=HISTORY_MAXLEN)

    # ── fold API (与 TurnControlUnit 同形) ─────────────────────────────

    def init(self, header: Any) -> None:
        del header
        # 不持有 caller state;fold 期间每次从空 init 重新走 events。
        # PR-A 仅暴露 ``current`` + ``confidence_history``,不引入
        # mutable projection state 概念。
        return None

    def apply(self, event: SessionEvent) -> None:
        """Fold one Session event into the projection。

        只关心 ``task_progress.commit.v1``;其它类型 no-op(保证与未来
        共享同一 Session 流时不互相污染)。
        """
        if event.type != _TASK_PROGRESS_COMMIT:
            return
        payload = event.data if isinstance(event.data, dict) else {}
        committed = TaskProgressCommitted(
            step_id=str(payload.get("step_id") or ""),
            completed=tuple(payload.get("completed") or ()),
            remaining=tuple(payload.get("remaining") or ()),
            confidence=float(payload.get("confidence") or 0.0),
            termination_reason=(
                str(payload["termination_reason"])
                if payload.get("termination_reason") is not None
                else None
            ),
        )
        prev = self._state if self._state is not None else TaskProgress()
        merged_completed = tuple(sorted(set(prev.completed) | set(committed.completed)))
        self._state = TaskProgress(
            completed=merged_completed,
            remaining=committed.remaining,
            confidence=committed.confidence,
            termination_reason=committed.termination_reason,
        )
        self._confidence_history.append(committed.confidence)
        self._completed_history.append(merged_completed)

    def fold(self, session: Any) -> None:
        """从 Session snapshot 单流 fold(SSR-0191 Wave D + ADR-0214 §4.1.2)。

        ``session`` duck-type 探测 ``snapshot_events()``;无则 no-op。
        """
        snapshot = getattr(session, "snapshot_events", None)
        if not callable(snapshot):
            return
        for event in cast("Any", snapshot)():
            self.apply(event)

    # ── 查询面 (供 Gate / Prompt 注入使用) ──────────────────────────────

    @property
    def current(self) -> TaskProgress:
        """fold 后的当前 ``TaskProgress``;空 events → ``TaskProgress()`` 默认。"""
        if self._state is None:
            return TaskProgress()
        return self._state

    @property
    def confidence_history(self) -> tuple[float, ...]:
        """最近的 confidence 历史,长度 ≤ ``HISTORY_MAXLEN``。"""
        return tuple(self._confidence_history)

    @property
    def completed_history(self) -> tuple[tuple[str, ...], ...]:
        """最近每个 fold step 后的 completed 集合(用于 PR-B completed-flatline 判定)。

        每个元素是该 step 累计的 completed 集合(单调合并后),长度 ≤
        ``HISTORY_MAXLEN``。PR-A 不读取本字段;PR-B MultiToolLoopBreakerGate
        用它判断"最近 K 步 completed 集合无新增"。
        """
        return tuple(self._completed_history)

    @property
    def last_step_id(self) -> str | None:
        """最近一次 task_progress.commit.v1 的 step_id;无则 None。"""
        # 我们没有显式记录 last_step_id(避免冗余);通过 append 时的 step_id
        # 也不在这里保留;Gate 需要 step_id 时用 Session 直接读 fold。
        # 本属性作为占位,避免调用方对命名误解;返回 None 走 no-step 路径。
        return None

    def is_stuck(self, window: int = 5, threshold: float = 0.1) -> bool:
        """最近 K 步 confidence 下降 > threshold → stuck。

        :param window: 滑动窗口大小;若历史长度 < window → False。
        :param threshold: 下降阈值;``confidence_history[-1] - confidence_history[-window] < -threshold`` 触发。
        """
        history = self.confidence_history
        if len(history) < window:
            return False
        delta = history[-1] - history[-window]
        return delta < -threshold
