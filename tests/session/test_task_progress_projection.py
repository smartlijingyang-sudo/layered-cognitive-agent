"""TaskProgressProjection fold invariants (ADR-0214 §4.2 / §4.3).

- 空 events → default
- 单调递增 completed → 不变式
- confidence_history 长度 + 顺序
- resume fold 幂等(同 events fold 两次结果一致)
- is_stuck 判定(窗口不够 / 下降 / 上升 / 持平)
"""

from __future__ import annotations

from lca.contracts.models.core.execution.task_progress import TaskProgress
from lca.plugins.session.task_progress.projection import (
    HISTORY_MAXLEN,
    TaskProgressProjection,
)
from lca_kernel.events.session.session import SessionEvent


def _event(
    *,
    seq: int,
    step_id: str,
    completed: tuple[str, ...] = (),
    remaining: tuple[str, ...] = (),
    confidence: float = 0.0,
    termination_reason: str | None = None,
    type_: str = "task_progress.commit.v1",
) -> SessionEvent:
    """Construct a SessionEvent carrying a TaskProgressCommitted payload."""
    payload = {
        "step_id": step_id,
        "completed": list(completed),
        "remaining": list(remaining),
        "confidence": confidence,
        "termination_reason": termination_reason,
    }
    return SessionEvent(
        type=type_,
        seq=seq,
        time=1_000 + seq,
        data=payload,
        session_id="test-session",
    )


class _FakeSession:
    """duck-type Session for ``TaskProgressProjection.fold(session)``."""

    def __init__(self, events: tuple[SessionEvent, ...]) -> None:
        self._events = events

    def snapshot_events(
        self,
        from_seq: int = 0,
        to_seq_exclusive: int | None = None,
    ) -> tuple[SessionEvent, ...]:
        lo, hi = from_seq, to_seq_exclusive if to_seq_exclusive is not None else len(self._events)
        return self._events[lo:hi]


def test_empty_events_yields_default() -> None:
    """空 events → current 是 TaskProgress() 默认值。"""
    proj = TaskProgressProjection()
    assert proj.current == TaskProgress()
    assert proj.confidence_history == ()


def test_fold_session_with_no_snapshot_is_noop() -> None:
    """session 没有 snapshot_events() → fold 不报错,state 仍默认。"""
    proj = TaskProgressProjection()

    class _NoSnapshot:
        pass

    proj.fold(_NoSnapshot())
    assert proj.current == TaskProgress()


def test_non_task_progress_events_are_ignored() -> None:
    """非 ``task_progress.commit.v1`` 事件 → no-op。"""
    proj = TaskProgressProjection()
    noise = SessionEvent(
        type="turn.ended.v1",
        seq=0,
        time=1_000,
        data={"turn": 1, "reason": "stop"},
        session_id="t",
    )
    proj.apply(noise)
    assert proj.current == TaskProgress()
    assert proj.confidence_history == ()


def test_completed_monotonically_grows() -> None:
    """单调:旧 ['a'] + 新 ['a','b'] → 当前 ['a','b']。"""
    proj = TaskProgressProjection()
    proj.apply(_event(seq=0, step_id="s0", completed=("a",), confidence=0.3))
    proj.apply(_event(seq=1, step_id="s1", completed=("a", "b"), confidence=0.5))

    assert proj.current.completed == ("a", "b")
    assert proj.current.confidence == 0.5


def test_completed_subset_does_not_shrink() -> None:
    """不缩:旧 ['a','b'] + 新 ['a'] → 保持 ['a','b']。"""
    proj = TaskProgressProjection()
    proj.apply(_event(seq=0, step_id="s0", completed=("a", "b"), confidence=0.5))
    proj.apply(_event(seq=1, step_id="s1", completed=("a",), confidence=0.4))

    assert set(proj.current.completed) == {"a", "b"}


def test_confidence_history_length_and_order() -> None:
    """confidence_history:顺序 = apply 顺序;长度 ≤ HISTORY_MAXLEN。"""
    proj = TaskProgressProjection()
    confidences = [0.1, 0.2, 0.3, 0.4, 0.5]
    for idx, conf in enumerate(confidences):
        proj.apply(_event(seq=idx, step_id=f"s{idx}", confidence=conf))

    assert proj.confidence_history == (0.1, 0.2, 0.3, 0.4, 0.5)


def test_confidence_history_caps_at_maxlen() -> None:
    """history 长度 ≥ HISTORY_MAXLEN → deque(maxlen) 自动丢弃最早条目。"""
    proj = TaskProgressProjection()
    for idx in range(HISTORY_MAXLEN + 5):
        proj.apply(_event(seq=idx, step_id=f"s{idx}", confidence=idx / 100.0))

    assert len(proj.confidence_history) == HISTORY_MAXLEN
    # 最早 5 条被丢弃;尾部 5 条 = seq 10..14
    tail = proj.confidence_history[-5:]
    assert tail == tuple(i / 100.0 for i in range(10, 15))


def test_resume_fold_is_idempotent() -> None:
    """C9:同 events fold 两次结果一致(幂等 / 重入)。"""
    events = tuple(
        _event(
            seq=i,
            step_id=f"s{i}",
            completed=(f"item{i}",),
            remaining=("todo",),
            confidence=0.4 + i * 0.05,
        )
        for i in range(3)
    )
    session = _FakeSession(events)

    proj_a = TaskProgressProjection()
    proj_a.fold(session)

    proj_b = TaskProgressProjection()
    proj_b.fold(session)

    assert proj_a.current == proj_b.current
    assert proj_a.confidence_history == proj_b.confidence_history


def test_is_stuck_false_when_history_shorter_than_window() -> None:
    """窗口不够 → False。"""
    proj = TaskProgressProjection()
    proj.apply(_event(seq=0, step_id="s0", confidence=0.9))
    proj.apply(_event(seq=1, step_id="s1", confidence=0.1))
    # 长度 2 < window 5 → not stuck
    assert proj.is_stuck(window=5, threshold=0.1) is False


def test_is_stuck_true_when_confidence_drops_below_threshold() -> None:
    """窗口内 confidence 下降 > threshold → True。"""
    proj = TaskProgressProjection()
    confidences = [0.9, 0.8, 0.7, 0.6, 0.1]  # -window[0] (0.9) → 0.1:delta=-0.8
    for idx, conf in enumerate(confidences):
        proj.apply(_event(seq=idx, step_id=f"s{idx}", confidence=conf))

    assert proj.is_stuck(window=5, threshold=0.1) is True


def test_is_stuck_false_when_confidence_rises() -> None:
    """窗口内 confidence 上升 → False。"""
    proj = TaskProgressProjection()
    for idx, conf in enumerate([0.1, 0.2, 0.3, 0.4, 0.9]):
        proj.apply(_event(seq=idx, step_id=f"s{idx}", confidence=conf))
    assert proj.is_stuck(window=5, threshold=0.1) is False


def test_is_stuck_false_when_within_threshold() -> None:
    """窗口内 confidence 变化在阈值内 → False(持平)。"""
    proj = TaskProgressProjection()
    for idx, conf in enumerate([0.50, 0.50, 0.50, 0.50, 0.45]):
        proj.apply(_event(seq=idx, step_id=f"s{idx}", confidence=conf))
    # -0.05 > -0.1 阈值 → 不算 stuck
    assert proj.is_stuck(window=5, threshold=0.1) is False


def test_fold_preserves_termination_reason() -> None:
    """``termination_reason`` 单字段直接覆盖(非单调)。"""
    proj = TaskProgressProjection()
    proj.apply(_event(seq=0, step_id="s0", confidence=0.5, termination_reason="budget"))
    proj.apply(_event(seq=1, step_id="s1", confidence=0.5, termination_reason="max_steps"))
    assert proj.current.termination_reason == "max_steps"


def test_projection_apply_rejects_out_of_range_confidence() -> None:
    """projection.apply() 重建 ``TaskProgressCommitted`` 时,confidence 越界抛 :class:`ContractViolation`."""
    import pytest as _pytest

    from lca.contracts.errors import ContractViolation

    proj = TaskProgressProjection()
    bad_event = SessionEvent(
        type="task_progress.commit.v1",
        seq=0,
        time=1000,
        data={
            "step_id": "s",
            "completed": [],
            "remaining": [],
            "confidence": 1.5,  # 越界
            "termination_reason": None,
        },
        session_id="t",
    )
    with _pytest.raises(ContractViolation):
        proj.apply(bad_event)
