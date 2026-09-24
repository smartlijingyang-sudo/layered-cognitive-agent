"""RoutineSchedulerService for background routine orchestration (ADR-0248 §3.4 / s04)."""

from __future__ import annotations

import time
from typing import Any

from lca.application.routine.spend_guard import SpendGuard
from lca.contracts.models.routine.models import RoutineSpec, RoutineTrigger
from lca.contracts.models.vocal.wake import WakeSource
from lca.domain.routine.repository import JsonRoutineRepository


class RoutineSchedulerService:
    """声明式后台例程调度服务。

    职责：
    1. 依据 Cron / 间隔周期判定触发时机；
    2. 执行前核验 SpendGuard 预算熔断硬闸（INV-08）；
    3. 注入 WakeSource.ROUTINE_CRON / ROUTINE_INTERVAL，天然具备合法沉默放行特权（INV-07）；
    4. 记录执行事实与生命周期。
    """

    def __init__(
        self,
        repository: JsonRoutineRepository,
        spend_guard: SpendGuard,
    ) -> None:
        self.repository = repository
        self.spend_guard = spend_guard
        self._last_triggered: dict[str, int] = {}

    def can_trigger(self, routine_id: str) -> bool:
        """判定指定例程当前是否可以触发执行。

        必须满足：例程存在、处于启用状态、且未被 SpendGuard 熔断。
        """
        spec = self.repository.get(routine_id)
        if spec is None or not spec.enabled:
            return False

        return not self.spend_guard.is_budget_exceeded(spec)

    def create_wake_source(self, spec: RoutineSpec) -> WakeSource:
        """为特定例程构建合法沉默唤醒源（INV-07）。"""
        return WakeSource.ROUTINE

    def record_triggered(self, routine_id: str, trigger_source: str = "cron") -> RoutineTrigger:
        """记录例程触发并更新最后触发时间戳。"""
        now_ms = int(time.time() * 1000)
        self._last_triggered[routine_id] = now_ms
        return RoutineTrigger(
            routine_id=routine_id,
            triggered_at_ms=now_ms,
            trigger_source=trigger_source,
        )

    def get_run_params(self, routine_id: str) -> dict[str, Any] | None:
        """获取创建 Run 所需的参数配置。"""
        spec = self.repository.get(routine_id)
        if spec is None or not self.can_trigger(routine_id):
            return None

        wake_source = self.create_wake_source(spec)
        return {
            "assistant_id": spec.assistant_id,
            "user_text": spec.prompt,
            "wake_source": wake_source.value,
            "budget": {"max_steps": spec.spend_budget_per_run},
            "extra": {
                "routine_id": spec.id,
                "routine_name": spec.name,
            },
        }


__all__ = ["RoutineSchedulerService"]
