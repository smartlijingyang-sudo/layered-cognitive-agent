"""RoutineSchedulerService for background routine orchestration (ADR-0248 §3.4 / s04)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lca.application.routine.locks import RoutineFileLock
from lca.application.routine.spend_guard import SpendGuard
from lca.application.routine.verdicts import SkipReason, TriggerDecision
from lca.contracts.atoms.ids.ids import utc_now_ms
from lca.contracts.models.routine.models import RoutineSpec, RoutineTrigger
from lca.contracts.models.vocal.wake import WakeSource
from lca.domain.routine.repository import JsonRoutineRepository

#: Due-window fallback for specs that declare no ``interval_s``
#: (ADR-0263 §8 时间窗口判定需要一个窗口；生产三路 cron 均为整点小时级，
#: 取 3600s 为约定值，见 RoutineSpec.interval_s docstring)。
DEFAULT_DUE_WINDOW_S = 3_600


class RoutineSchedulerService:
    """声明式后台例程调度服务。

    职责：
    1. 依据 Cron / 间隔周期判定触发时机；
    2. 执行前核验 SpendGuard 预算熔断硬闸（INV-08）；
    3. 注入 WakeSource.ROUTINE_CRON / ROUTINE_INTERVAL，天然具备合法沉默放行特权（INV-07）；
    4. 记录执行事实与生命周期。

    ADR-0263（C1–C4）扩展：
    - ``evaluate()`` 是 ``can_trigger()`` 的契约升级：静默 False 变为显式
      verdict（``TriggerDecision``），判定顺序固定为
      enabled → 互斥锁 → SpendGuard → 时间窗口（§8）；
    - 互斥需要锁感知：构造时传入 ``lock_dir``（tests lane 留的开放设计点，
      本实现选构造参数形态）；不传则跳过互斥判定（无锁感知）；
    - ``record_triggered()`` 把触发记录下沉到 repository（C4），进程重启
      后仍可按持久化时间戳判定，不立即重复触发（T3）。
    """

    def __init__(
        self,
        repository: JsonRoutineRepository,
        spend_guard: SpendGuard,
        lock_dir: str | Path | None = None,
    ) -> None:
        self.repository = repository
        self.spend_guard = spend_guard
        self._lock_dir = Path(lock_dir).expanduser().resolve() if lock_dir is not None else None
        if self._lock_dir is not None:
            self._lock_dir.mkdir(parents=True, exist_ok=True)

    def can_trigger(self, routine_id: str) -> bool:
        """判定指定例程当前是否可以触发执行。

        必须满足：例程存在、处于启用状态、且未被 SpendGuard 熔断。
        兼容保留：不含互斥与时间窗口判定，需要显式 verdict 请用 ``evaluate()``。
        """
        spec = self.repository.get(routine_id)
        if spec is None or not spec.enabled:
            return False

        return not self.spend_guard.is_budget_exceeded(spec)

    def evaluate(self, routine_id: str) -> TriggerDecision:
        """触发判定的契约升级版：返回显式 verdict 而非静默布尔值。

        判定顺序（ADR-0263 §8）：enabled → 互斥锁 → SpendGuard → 时间窗口。
        """
        spec = self.repository.get(routine_id)
        if spec is None or not spec.enabled:
            return TriggerDecision(allowed=False, skip_reason=SkipReason.DISABLED)

        if self._lock_dir is not None:
            lock = RoutineFileLock(self._lock_dir, routine_id, routine_interval_s=spec.interval_s)
            if lock.is_locked():
                return TriggerDecision(allowed=False, skip_reason=SkipReason.ALREADY_RUNNING)

        if self.spend_guard.is_budget_exceeded(spec):
            return TriggerDecision(allowed=False, skip_reason=SkipReason.BUDGET_EXCEEDED)

        last = self.repository.get_last_trigger(routine_id)
        if last is not None:
            window_s = spec.interval_s if spec.interval_s is not None else DEFAULT_DUE_WINDOW_S
            if utc_now_ms() - last.triggered_at_ms < window_s * 1000:
                return TriggerDecision(allowed=False, skip_reason=SkipReason.NOT_DUE)

        return TriggerDecision(allowed=True)

    def create_wake_source(self, spec: RoutineSpec) -> WakeSource:
        """为特定例程构建合法沉默唤醒源（INV-07）。"""
        return WakeSource.ROUTINE

    def record_triggered(self, routine_id: str, trigger_source: str = "cron") -> RoutineTrigger:
        """记录例程触发并把触发时间戳下沉到 repository（ADR-0263 C4）。

        幂等：同 routine_id 连续记录即 last-write-wins，不产生重复副作用。
        """
        trigger = RoutineTrigger(
            routine_id=routine_id,
            triggered_at_ms=utc_now_ms(),
            trigger_source=trigger_source,
        )
        self.repository.save_trigger(trigger)
        return trigger

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


__all__ = ["DEFAULT_DUE_WINDOW_S", "RoutineSchedulerService"]
