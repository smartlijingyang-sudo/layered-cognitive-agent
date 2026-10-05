"""ADR-0263《例程调度互斥与自愈》验收契约测试（T1–T4）。

【预期红契约钉】2026-10-03 实证：0263 源码侧尚未落地——
lca/application/routine/ 只有判定三件套（can_trigger/record_triggered/
get_run_params），无互斥锁、无 SKIP verdict、无持久化下沉、无 tick 驱动
（生产无 tick 调用方，ADR §实证缺口）。本文件按 ADR T1–T4 + §9 裁决
把验收标准钉成测试：当前全部预期红；quality lane 实现后转绿，不改测试。

tests lane 定义的契约 seam（quality lane 实现时遵循；开放设计点已标注）：
- lca.application.routine.locks.RoutineFileLock(lock_dir, routine_id, stale_after_s=None)
  acquire() -> bool / release() / reclaim_stale() -> ReclaimTrace | None。
  锁文件 <lock_dir>/<routine_id>.lock，JSON {"owner": str, "heartbeat_ms": int}
  （锁文件格式是本契约的一部分：T2 的"写过期锁文件模拟"依赖它）。
  stale 默认 2×interval、绝对上限 90min（§9 裁决①②）。
- lca.application.routine.verdicts：SkipReason（ALREADY_RUNNING /
  BUDGET_EXCEEDED / NOT_DUE / DISABLED），TriggerDecision(allowed: bool,
  skip_reason: SkipReason | None)。
- RoutineSchedulerService.evaluate(routine_id) -> TriggerDecision
  （can_trigger 的契约升级：静默 False → 显式 verdict；can_trigger 保留兼容）。
  判定顺序：enabled → 互斥锁 → SpendGuard → 时间窗口（ADR §8）。
  开放设计点：scheduler 如何获得锁感知（构造参数 lock_dir 还是方法参数）
  由 quality lane 定；本测试按构造参数 lock_dir 编写。
- T5（失败隔离）未在本文件钉：验收主体是 tick 循环，而生产尚无 tick
  调用方（ADR §实证缺口④）；待 quality lane 的 tick 驱动单元（§10）
  落地后补钉。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

try:
    from lca.application.routine.locks import RoutineFileLock
except ImportError:  # ADR-0263 C1 未落地
    RoutineFileLock = None  # type: ignore[assignment]

try:
    from lca.application.routine.verdicts import SkipReason, TriggerDecision
except ImportError:  # ADR-0263 C3 未落地
    SkipReason = None  # type: ignore[assignment]
    TriggerDecision = None  # type: ignore[assignment]

from lca.application.routine.scheduler import RoutineSchedulerService
from lca.application.routine.spend_guard import SpendGuard
from lca.contracts.models.routine.models import RoutineSpec
from lca.domain.routine.repository import JsonRoutineRepository


def _require(name: str, sym):
    assert sym is not None, f"ADR-0263 未落地：{name} 缺席（预期红契约钉）"
    return sym


def _make_spec(routine_id: str = "rt_demo", **kwargs) -> RoutineSpec:
    return RoutineSpec(
        id=routine_id,
        name="demo routine",
        prompt="demo prompt",
        assistant_id="asst-1",
        **kwargs,
    )


def _make_scheduler(tmp_path: Path, spec: RoutineSpec | None = None):
    repo_dir = tmp_path / "repo"
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    repo = JsonRoutineRepository(repo_dir)
    guard = SpendGuard()
    if spec is None:
        spec = _make_spec()
    repo.save(spec)
    # 开放设计点：lock_dir 构造参数形态由 quality lane 定（见模块 docstring）。
    scheduler = RoutineSchedulerService(
        repository=repo, spend_guard=guard, lock_dir=lock_dir
    )
    return scheduler, spec, guard, lock_dir


class TestT1ConcurrentTrigger:
    """T1 并发触发：同时触发同一 routine 两次，第二次返回 SKIP(ALREADY_RUNNING)。"""

    def test_second_acquire_fails_without_queueing(self, tmp_path):
        lock_cls = _require(
            "lca.application.routine.locks.RoutineFileLock", RoutineFileLock
        )
        first = lock_cls(lock_dir=tmp_path, routine_id="rt_demo")
        second = lock_cls(lock_dir=tmp_path, routine_id="rt_demo")
        assert first.acquire() is True
        assert second.acquire() is False  # 不排队、不等待
        first.release()
        assert second.acquire() is True  # 释放后可取得

    def test_evaluate_returns_skip_already_running_when_locked(self, tmp_path):
        lock_cls = _require(
            "lca.application.routine.locks.RoutineFileLock", RoutineFileLock
        )
        _require("lca.application.routine.verdicts.SkipReason", SkipReason)
        scheduler, spec, _guard, lock_dir = _make_scheduler(tmp_path)
        holder = lock_cls(lock_dir=lock_dir, routine_id=spec.id)
        assert holder.acquire() is True
        decision = scheduler.evaluate(spec.id)
        assert decision.allowed is False
        assert decision.skip_reason == SkipReason.ALREADY_RUNNING


class TestT2StaleLockSelfHealing:
    """T2 锁自愈：持锁进程被 kill -9 后，stale 阈值过后新触发成功取得锁，并留有收割痕迹。"""

    def test_stale_lock_reclaimed_and_reacquired(self, tmp_path):
        lock_cls = _require(
            "lca.application.routine.locks.RoutineFileLock", RoutineFileLock
        )
        lock = lock_cls(lock_dir=tmp_path, routine_id="rt_demo", stale_after_s=0.05)
        # 模拟 kill -9：持锁者已死，写一个心跳过期的锁文件（本契约定义的格式）。
        stale_ms = int(time.time() * 1000) - 60_000
        (tmp_path / "rt_demo.lock").write_text(
            json.dumps({"owner": "dead-holder", "heartbeat_ms": stale_ms})
        )
        info = lock.reclaim_stale()
        assert info is not None
        assert info.previous_owner == "dead-holder"  # 收割留痕：原 owner 被记录
        assert info.held_ms >= 30_000
        assert lock.acquire() is True  # 收割后新触发可取得

    def test_fresh_lock_not_reaped(self, tmp_path):
        lock_cls = _require(
            "lca.application.routine.locks.RoutineFileLock", RoutineFileLock
        )
        lock = lock_cls(lock_dir=tmp_path, routine_id="rt_demo", stale_after_s=3_600)
        assert lock.acquire() is True
        assert lock.reclaim_stale() is None  # 活锁不许被收割


class TestT3RestartDoesNotRetrigger:
    """T3 重启不丢：进程重启后 _last_triggered 仍有效，不立即重复触发。"""

    def test_restart_within_window_does_not_retrigger(self, tmp_path):
        _require("lca.application.routine.verdicts.SkipReason", SkipReason)
        scheduler1, spec, _guard, _lock_dir = _make_scheduler(tmp_path)
        scheduler1.record_triggered(spec.id)
        # 模拟进程重启：全新 scheduler 实例，同一 repository（持久化下沉）。
        scheduler2, _spec, _guard2, _lock_dir2 = _make_scheduler(tmp_path)
        decision = scheduler2.evaluate(spec.id)
        assert decision.allowed is False  # 窗口内不重复触发


class TestT4BudgetGate:
    """T4 预算闸：SpendGuard 熔断时触发判定返回 SKIP(BUDGET_EXCEEDED)
    （can_trigger 现有 false 语义升契约）。"""

    def test_tripped_budget_returns_skip_budget_exceeded(self, tmp_path):
        _require("lca.application.routine.verdicts.SkipReason", SkipReason)
        scheduler, spec, guard, _lock_dir = _make_scheduler(tmp_path)
        guard.record_consumption(spec.id, spec.daily_budget_tokens)  # 确定性熔断
        decision = scheduler.evaluate(spec.id)
        assert decision.allowed is False
        assert decision.skip_reason == SkipReason.BUDGET_EXCEEDED

    def test_disabled_routine_returns_skip_disabled(self, tmp_path):
        _require("lca.application.routine.verdicts.SkipReason", SkipReason)
        spec = _make_spec(enabled=False)
        scheduler, _spec, _guard, _lock_dir = _make_scheduler(tmp_path, spec=spec)
        decision = scheduler.evaluate(spec.id)
        assert decision.allowed is False
        assert decision.skip_reason == SkipReason.DISABLED
