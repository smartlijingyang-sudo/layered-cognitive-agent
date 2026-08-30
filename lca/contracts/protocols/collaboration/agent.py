"""L3 Agent entry shape — single-agent run / resume / cancel only.

Other collaboration / budget concerns were extracted (2026-08-30 cleanup):
  - TeamUnit       → collaboration/team_unit.py
  - BudgetPolicy   → gate/budget_policy.py
  - BudgetAware    → removed (marker interfaces are OOP anti-pattern;
                    BudgetPolicy now operates on data, not on agent objects)
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.models.core.message import AgentMessage
from lca.contracts.models.core.result import Result
from lca.contracts.models.core.state import StateSnapshot
from lca.contracts.models.team.role_team import RoleProfile
from lca.contracts.models.team.run_context import RunContext


@runtime_checkable
class AgentUnit(Protocol):
    """Single-agent entry: run / resume / cancel."""

    role_profile: RoleProfile

    async def run(
        self,
        task: str | AgentMessage,
        ctx: RunContext | None = None,
    ) -> Result: ...

    async def resume(
        self, snapshot: StateSnapshot, input: str | AgentMessage | None = None
    ) -> Result: ...

    async def cancel(self) -> None: ...
