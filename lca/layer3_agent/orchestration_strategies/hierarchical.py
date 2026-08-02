"""HierarchicalStrategy — supervisor delegates and synthesizes."""

from __future__ import annotations

from lca.contracts.enums import RoleMode
from lca.contracts.protocols import TeamContext, TeamProcessStrategy
from lca.contracts.result import Result
from lca.contracts.run_context import RunContext


class HierarchicalStrategy(TeamProcessStrategy):
    """Supervisor-only path; member_status carried via RunContext."""

    async def run(self, context: TeamContext, objective: str) -> Result:
        if context.supervisor is None:
            raise ValueError("Hierarchical 模式需要 Supervisor")
        ctx = RunContext(
            member_status=context.member_status,
            teammates=list(context.teammates),
            role_mode=RoleMode.SUPERVISOR,
        )
        return await context.supervisor.run(objective, ctx)
