"""HierarchicalStrategy —— Supervisor 单向委派、汇总。"""

from __future__ import annotations

from typing import cast

from lca.contracts.protocols import OrchestrationContext, OrchestrationStrategy
from lca.contracts.result import Result


class HierarchicalStrategy(OrchestrationStrategy):
    """Supervisor 单向委派、汇总。"""

    async def run(self, context: OrchestrationContext, objective: str) -> Result:
        if context.supervisor is None:
            raise ValueError("Hierarchical 模式需要 Supervisor")
        if context.transport is not None:
            context.supervisor.bind_team(context.transport, context.roster_desc)
        return cast("Result", await context.supervisor.execute(objective))
