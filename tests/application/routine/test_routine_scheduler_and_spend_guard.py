"""Tests for Routine Repository, SpendGuard, and Scheduler (ADR-0248 §3.4, §5.1 / s04, s14).

Invariants tested:
- INV-07: 例程合法沉默放行且 0 垃圾通知（is_silence_allowed=True，0 消息正常收敛）。
- INV-08: Token 消耗超预算立即熔断暂停（SpendGuard 阻断触发）。
"""

import pytest

from lca.application.routine.scheduler import RoutineSchedulerService
from lca.application.routine.spend_guard import SpendGuard
from lca.contracts.models.routine.models import RoutineSpec
from lca.contracts.models.vocal.wake import WakeSource
from lca.domain.routine.repository import JsonRoutineRepository
from lca.infrastructure.vocal.gate import GatedVocalGate
from lca.infrastructure.vocal.settle_guard import VocalSettleGuard


def test_spend_guard_daily_budget_enforcement():
    """INV-08: Token 消耗超预算立即熔断暂停。"""
    guard = SpendGuard()
    spec = RoutineSpec(
        id="rt_build_checker",
        name="构建健康监测",
        prompt="检查 CI 构建状态",
        assistant_id="asst_arch_1",
        daily_budget_tokens=1000,
    )

    # 消费 800 tokens，未超限
    guard.record_consumption("rt_build_checker", tokens_used=800)
    assert guard.is_budget_exceeded(spec) is False
    assert guard.get_consumed_tokens("rt_build_checker") == 800

    # 再次消费 300 tokens，累计 1100 tokens > 1000 tokens，触发熔断
    guard.record_consumption("rt_build_checker", tokens_used=300)
    assert guard.is_budget_exceeded(spec) is True


def test_routine_repository_crud(tmp_path):
    repo = JsonRoutineRepository(storage_dir=tmp_path / "routines")
    spec = RoutineSpec(
        id="rt_daily_summary",
        name="每日总结",
        cron_expr="0 18 * * *",
        prompt="汇总今日工作日志",
        assistant_id="asst_1",
        daily_budget_tokens=50_000,
    )

    # 增
    repo.save(spec)
    # 查
    loaded = repo.get("rt_daily_summary")
    assert loaded is not None
    assert loaded.id == "rt_daily_summary"
    assert loaded.cron_expr == "0 18 * * *"

    # 查列表
    all_routines = repo.list_all()
    assert len(all_routines) == 1
    assert all_routines[0].id == "rt_daily_summary"

    # 删
    deleted = repo.delete("rt_daily_summary")
    assert deleted is True
    assert repo.get("rt_daily_summary") is None
    assert len(repo.list_all()) == 0


@pytest.mark.asyncio
async def test_routine_scheduler_legal_silence_and_spend_fusing(tmp_path):
    """INV-07 & INV-08: 验证例程合法沉默放行与超预算熔断。"""
    repo = JsonRoutineRepository(storage_dir=tmp_path / "routines")
    spend_guard = SpendGuard()
    scheduler = RoutineSchedulerService(repository=repo, spend_guard=spend_guard)

    spec = RoutineSpec(
        id="rt_silent_poll",
        name="静默轮询",
        interval_seconds=60,
        prompt="静默轮询外部指标",
        assistant_id="asst_1",
        daily_budget_tokens=500,
    )
    repo.save(spec)

    # 1. 验证常规例程执行拥有合法沉默属性（is_silence_allowed=True）
    gate = GatedVocalGate(operation_id="op_routine", wake_source=WakeSource.ROUTINE)
    assert gate.wake_context.is_silence_allowed is True

    # 0 交付结算时不应报错
    settle_guard = VocalSettleGuard(gate)
    assert settle_guard.validate_turn_settle() is True

    # 2. 模拟超预算并验证调度器阻断调度
    spend_guard.record_consumption("rt_silent_poll", tokens_used=600)
    should_run = scheduler.can_trigger("rt_silent_poll")
    assert should_run is False  # 预算熔断拒绝执行
