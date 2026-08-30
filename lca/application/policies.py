"""Budget policy implementations — composition-time budget resolution.

Policies are registered under ComponentKind.BUDGET_POLICY (e.g. ``lead``).
"""

from __future__ import annotations

from lca.contracts.models.core.budget import (
    DEFAULT_MAX_WALL_CLOCK_SECONDS,
    LEAD_MIN_MAX_STEPS,
    BudgetLimits,
)
from lca.contracts.protocols import BudgetPolicy

LEAD_BUDGET_POLICY_KEY = "lead"
"""lead 预算策略在 ComponentRegistry(BUDGET_POLICY) 下的注册名。"""


class LeadBudgetPolicy(BudgetPolicy):
    """Lead budget floors — ensures team lead has adequate headroom."""

    def resolve(
        self,
        *,
        max_steps: int,
        max_wall_clock_seconds: int | None,
        role: str,
    ) -> BudgetLimits:
        del role  # currently unused: floor logic is role-agnostic.
        return BudgetLimits(
            max_steps=max(max_steps, LEAD_MIN_MAX_STEPS),
            max_wall_clock_seconds=max(max_wall_clock_seconds or 0, DEFAULT_MAX_WALL_CLOCK_SECONDS),
        )
