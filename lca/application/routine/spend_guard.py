"""SpendGuard consumption fuse and budget enforcement (ADR-0248 §5.1 / s14)."""

from __future__ import annotations

import datetime
from collections import defaultdict

from lca.contracts.models.routine.models import RoutineSpec


class SpendGuard:
    """例程消费硬护栏与 Token 熔断器。

    不变量：
    - INV-08: 当日 Token 消耗达到 daily_budget_tokens 时立即熔断，阻断后续触发。
    - 按自然日（UTC/本地）自动滚动预算。
    """

    def __init__(self) -> None:
        self._current_date: datetime.date = datetime.date.today()
        self._consumption: defaultdict[str, int] = defaultdict(int)

    def _roll_date_if_needed(self) -> None:
        today = datetime.date.today()
        if today != self._current_date:
            self._current_date = today
            self._consumption.clear()

    def record_consumption(self, routine_id: str, tokens_used: int) -> None:
        """记录指定例程消耗的 Token 数量。"""
        if tokens_used <= 0:
            return
        self._roll_date_if_needed()
        self._consumption[routine_id] += tokens_used

    def get_consumed_tokens(self, routine_id: str) -> int:
        """获取指定例程今日累计消耗的 Token 数量。"""
        self._roll_date_if_needed()
        return self._consumption[routine_id]

    def is_budget_exceeded(self, spec: RoutineSpec) -> bool:
        """检查指定例程今日消耗是否已超出预算上限（超限即熔断）。"""
        consumed = self.get_consumed_tokens(spec.id)
        return consumed >= spec.daily_budget_tokens

    def reset_daily(self, routine_id: str | None = None) -> None:
        """重置消费记录（供测试或管理员重置熔断态）。"""
        if routine_id is not None:
            self._consumption[routine_id] = 0
        else:
            self._consumption.clear()


__all__ = ["SpendGuard"]
