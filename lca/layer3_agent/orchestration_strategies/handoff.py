"""HandoffStrategy."""

from __future__ import annotations

from lca.contracts.protocols import OrchestrationContext, OrchestrationStrategy
from lca.contracts.result import Result
from lca.layer3_agent.member_invoke import invoke_members_sequential


class HandoffStrategy(OrchestrationStrategy):
    async def run(self, context: OrchestrationContext, objective: str) -> Result:
        return await invoke_members_sequential(
            context, objective, pass_output_as_next_task=False, stop_on_first_completed=True
        )
