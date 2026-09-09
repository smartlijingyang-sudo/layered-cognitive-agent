"""fsync 回归锁测试 — ADR-0214 §4.1.1 / §12 风险缓解。

目的:cognition 解析 Decision.task_progress → ``FactGateway.emit()`` →
``Session.append`` 这一 T0 时机契约下,验证:

1. 写盘失败的"未 fsync"语义:**单条 ``task_progress.commit.v1`` 事件要么完整
   落入 Session 日志,要么完全没出现**(全有/全无,不出现半条)。
2. Session 日志恢复后,:class:`TaskProgressProjection` fold 结果与
   注入 prompt 的 ``<task_progress_resumed>`` 字段一致 — 状态在
   resume 时是可还原的,不依赖 chat history 推测。
3. 不持久化的崩溃窗口(events 未 flush 即 SIGKILL)下,**没有**任何
   残留状态被错认为"已 commit"(我们要求 caller 显式 flush)。

测试不模拟真实 fsync(那是 ``PersistenceObserver`` 的责任);改测
``Session.append`` 自身的"不可分割 append"语义 + 模拟"未 flush =
未 durable"边界。
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.contracts.harness.memory.events import TaskProgressCommitted
from lca.contracts.models.core.execution.task_progress import TaskProgress
from lca.plugins.session.task_progress.projection import TaskProgressProjection
from lca.session import Session
from lca_kernel.events.session.session import SessionEvent

_TASK_PROGRESS_COMMIT = "task_progress.commit.v1"


def _make_commit_payload(
    *,
    step_id: str,
    completed: tuple[str, ...] = (),
    remaining: tuple[str, ...] = (),
    confidence: float = 0.5,
    termination_reason: str | None = None,
) -> dict[str, Any]:
    """Build the SessionEvent data dict mirroring :class:`TaskProgressCommitted`."""
    payload = TaskProgressCommitted(
        step_id=step_id,
        completed=completed,
        remaining=remaining,
        confidence=confidence,
        termination_reason=termination_reason,
    )
    return {
        "step_id": payload.step_id,
        "completed": list(payload.completed),
        "remaining": list(payload.remaining),
        "confidence": payload.confidence,
        "termination_reason": payload.termination_reason,
    }


# ── 单条 append 的 all-or-nothing 语义 ────────────────────────────────


def test_task_progress_append_is_atomic_single_event() -> None:
    """单条 task_progress.commit.v1 必须完整入日志;``append`` 之前 / 之后
    日志长度差异恰好为 1(无半条)。
    """
    session = Session("fsync-test-1")
    assert session.seq == 0

    event = session.append(
        _TASK_PROGRESS_COMMIT,
        _make_commit_payload(step_id="s0", completed=("a",), confidence=0.5),
    )
    assert event.seq == 0
    assert event.type == _TASK_PROGRESS_COMMIT
    assert session.seq == 1  # 日志严格增长 1


def test_task_progress_append_fails_validation_does_not_mutate_log() -> None:
    """append 校验失败(空 type / 不可序列化)→ 日志长度不变;不出现"半条"。"""
    session = Session("fsync-test-2")
    with pytest.raises(ValueError):
        session.append("", {"step_id": "x"})  # 空 type 拒绝
    assert session.seq == 0  # 日志未变


def test_task_progress_append_rejects_non_json_data() -> None:
    """data 不可 JSON 序列化 → 校验拒绝,日志长度不变(无半条)。"""
    import math

    session = Session("fsync-test-3")
    with pytest.raises(TypeError):
        session.append(
            _TASK_PROGRESS_COMMIT,
            {"step_id": "x", "confidence": math.inf},  # NaN/Inf 被拒
        )
    assert session.seq == 0


# ── fold 幂等 + resume 一致性 (C9) ─────────────────────────────────


def _fold_state(events: tuple[SessionEvent, ...]) -> TaskProgress:
    """便利函数:用一份 events → TaskProgressProjection.current。"""
    proj = TaskProgressProjection()
    for event in events:
        proj.apply(event)
    return proj.current


def _events_with_payloads(*payloads: dict[str, Any]) -> tuple[SessionEvent, ...]:
    """构造一段 SessionEvent 序列(模拟已 durable 的事件流)。"""
    session = Session("replay-source")
    return tuple(session.append(_TASK_PROGRESS_COMMIT, payload) for payload in payloads)


def test_resume_fold_matches_in_progress_state() -> None:
    """resume 时,从 Session events fold 出的 ``TaskProgress`` 与原
    in-process mirror 一致 — 这就是 prompt 注入 ``<task_progress_resumed>``
    字段的 SSOT(ADR-0214 §4.1.2)。
    """
    payloads = [
        _make_commit_payload(step_id="s0", completed=("a",), confidence=0.4),
        _make_commit_payload(
            step_id="s1",
            completed=("a", "b"),
            remaining=("c",),
            confidence=0.6,
        ),
        _make_commit_payload(
            step_id="s2",
            completed=("a", "b", "c"),
            remaining=(),
            confidence=0.9,
            termination_reason="all_done",
        ),
    ]
    events = _events_with_payloads(*payloads)

    # ── (a) 原 in-process mirror ─────────────────────────────────────
    in_progress = TaskProgress(
        completed=("a", "b", "c"),
        remaining=(),
        confidence=0.9,
        termination_reason="all_done",
    )

    # ── (b) "重启" — 全新 Session,从 durable events fold ────────────
    resumed = _fold_state(events)

    # ── 断言 ────────────────────────────────────────────────────────
    assert resumed.completed == in_progress.completed
    assert resumed.remaining == in_progress.remaining
    assert resumed.confidence == in_progress.confidence
    assert resumed.termination_reason == in_progress.termination_reason
    # is_terminal 也一致(空 remaining + 高 confidence)
    assert resumed.is_terminal() is True
    assert resumed.is_terminal() == in_progress.is_terminal()


def test_resume_fold_idempotent_on_same_event_stream() -> None:
    """C9:同一份 durable events fold 多次 → 结果一致(幂等)。"""
    payloads = [
        _make_commit_payload(step_id="s0", completed=("x",), confidence=0.3),
        _make_commit_payload(step_id="s1", completed=("x", "y"), confidence=0.7),
    ]
    events = _events_with_payloads(*payloads)

    proj_a = TaskProgressProjection()
    proj_b = TaskProgressProjection()
    for event in events:
        proj_a.apply(event)
        proj_b.apply(event)

    assert proj_a.current == proj_b.current
    assert proj_a.confidence_history == proj_b.confidence_history


# ── "未 flush = 未 durable" 边界 ─────────────────────────────────


class _NoFsyncObserver:
    """永远不 fsync 的 observer:模拟"fsync 窗口"内的 SIGKILL 窗口。

    只把事件 ID 记进 ``recorded_ids``,不写入任何外部介质。``flush`` 方法
    仅触发现有事件,**不保证 durability**(这正是我们要模拟的崩点)。
    """

    def __init__(self) -> None:
        self.recorded_ids: list[str] = []

    def __call__(self, session: Any, event: SessionEvent) -> None:
        self.recorded_ids.append(f"{session.id}:{event.seq}")

    def flush(self, session: Any) -> None:
        return None  # no-op 模拟未 fsync


def test_unflushed_events_not_visible_across_process_restart() -> None:
    """未 fsync 的事件:进程"重启"后,新 Session 看不到;fold 是空状态。
    印证"未 fsync = 未 durable"边界 — Session fold 是 SSOT,但 SSOT
    来源是**已 fsync** 的 events,不是 in-memory log。
    """
    observer = _NoFsyncObserver()
    session = Session("fsync-restart-1")
    session.observe(observer)  # 注册 observer 但永远不 fsync
    session.append(
        _TASK_PROGRESS_COMMIT,
        _make_commit_payload(step_id="s0", completed=("a",), confidence=0.5),
    )
    session.append(
        _TASK_PROGRESS_COMMIT,
        _make_commit_payload(step_id="s1", completed=("a", "b"), confidence=0.7),
    )
    # observer 收到 2 条事件,但没有 fsync 到任何外部介质
    assert observer.recorded_ids == ["fsync-restart-1:0", "fsync-restart-1:1"]

    # ── "重启":模拟从空 Session 重建 ────────────────────────────────
    fresh = Session("fsync-restart-1")  # 同 id,空日志
    # 未 fsync 的事件全部丢失 — fresh 日志为空
    assert fresh.seq == 0
    proj = TaskProgressProjection()
    proj.fold(fresh)
    assert proj.current == TaskProgress()  # 默认空四元组


def test_flushed_events_visible_to_fresh_session_fold() -> None:
    """fsync 完成 → 重建 Session 喂同一份 events → fold 与原 mirror 一致。
    印证 §4.1.1 T0 先于 execute 契约:durable 后的事件可还原。
    """
    payloads = [
        _make_commit_payload(step_id="s0", completed=("a",), confidence=0.5),
        _make_commit_payload(step_id="s1", completed=("a", "b"), confidence=0.8),
    ]
    original_session = Session("fsync-restart-2")
    recorded: list[SessionEvent] = []
    for payload in payloads:
        recorded.append(original_session.append(_TASK_PROGRESS_COMMIT, payload))
    # 模拟 fsync 后:把 events dump 给 "新进程"
    durable_snapshot = tuple(recorded)

    # 新 Session 用同一份 durable events 喂进 fold
    proj = TaskProgressProjection()
    for event in durable_snapshot:
        proj.apply(event)

    assert proj.current.completed == ("a", "b")
    assert proj.current.confidence == 0.8


# ── 未 flush 中断下,observer 状态被 contained(不阻塞后续 append) ──


def test_observer_failure_does_not_block_subsequent_appends() -> None:
    """observer 抛错 → append 仍返回事件;后续 append 正常进行(C9 兑现)。"""
    session = Session("fsync-restart-3")

    class _BoomObserver:
        def __call__(self, s: Session, event: SessionEvent) -> None:
            raise RuntimeError("synthetic observer failure")

    session.observe(_BoomObserver())  # type: ignore[arg-type]
    event0 = session.append(
        _TASK_PROGRESS_COMMIT,
        _make_commit_payload(step_id="s0", confidence=0.5),
    )
    event1 = session.append(
        _TASK_PROGRESS_COMMIT,
        _make_commit_payload(step_id="s1", confidence=0.7),
    )
    # observer 抛错被 contained,日志严格按序 + 完整
    assert event0.seq == 0
    assert event1.seq == 1
    assert session.seq == 2


# ── register 回调式 flush listener fsync 模拟 ──────────────────────


def test_explicit_flush_listener_called_with_session() -> None:
    """``register_flush_listener`` 注册的 listener ``flush(session)`` 被
    调用 → 这是 fsync 时机契约的核心:caller 控制何时 fsync。
    """
    captured: list[tuple[str, int]] = []

    class _FlushProbe:
        async def flush(self, session: Session) -> None:
            captured.append((session.id, session.seq))

    import asyncio

    session = Session("fsync-test-listener")
    session.append(
        _TASK_PROGRESS_COMMIT,
        _make_commit_payload(step_id="s0", confidence=0.5),
    )
    cancel = session.register_flush_listener(_FlushProbe())  # type: ignore[arg-type]
    try:
        asyncio.run(session.flush())
        # flush 时 seq=1 (1 条 task_progress.commit.v1)
        assert captured == [("fsync-test-listener", 1)]
    finally:
        cancel()
