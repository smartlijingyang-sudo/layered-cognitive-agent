"""Budget policy seam — operates on budget data, not on agent objects.

The previous design required a ``BudgetAware`` marker interface on every
agent that participated in budget resolution. That marker leaked coupling
between the policy seam and the agent object graph, and the marker name
was an "Aware" anti-pattern (descriptive predicate, not a contract).

The new design resolves budgets from primitive values:
``resolve(*, max_steps, max_wall_clock_seconds, role) -> BudgetLimits``.
Callers extract the values from their AgentUnit and pass them in. The
policy seam no longer cares which concrete agent produced them.

Migration (2026-08-30):
  - BudgetAware class deleted (no replacement; consumers pass data)
  - BudgetPolicy.resolve signature changed to keyword-only data params
  - LeadBudgetPolicy (lca/application/policies.py) implements new signature
  - agent_assembly.promote_lead unpacks lead agent and forwards data
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.models.core.budget import BudgetLimits


@runtime_checkable
class BudgetPolicy(Protocol):
    """组合时预算解析策略——单一真相源。

    resolve 返回该 agent 在其角色下应得的有效预算值。
    调用方 apply 返回值，不重算阈值。
    """

    def resolve(
        self,
        *,
        max_steps: int,
        max_wall_clock_seconds: int | None,
        role: str,
    ) -> BudgetLimits: ...
