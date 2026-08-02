"""Budget policy implementations — composition-time budget resolution strategies.

Each policy resolves an agent's budget fields to effective values
appropriate for its role. Policies are registered in the component
registry under ComponentKind.BUDGET_POLICY and resolved by name
(e.g. "supervisor").
"""

from __future__ import annotations

from lca.contracts.budget import (
    DEFAULT_MAX_WALL_CLOCK_SECONDS,
    SUPERVISOR_MIN_MAX_STEPS,
    BudgetLimits,
)
from lca.contracts.protocols import BudgetAware, BudgetPolicy


class SupervisorBudgetPolicy(BudgetPolicy):
    """Supervisor budget floors — ensures team lead has adequate headroom."""

    def resolve(self, agent: BudgetAware) -> BudgetLimits:
        return BudgetLimits(
            max_steps=max(agent.max_steps, SUPERVISOR_MIN_MAX_STEPS),
            max_wall_clock_seconds=max(
                agent.max_wall_clock_seconds or 0, DEFAULT_MAX_WALL_CLOCK_SECONDS
            ),
        )
