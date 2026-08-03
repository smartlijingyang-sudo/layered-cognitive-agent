"""TeamOrchestrator — closed team handle; strategies only run."""

from __future__ import annotations

from lca.contracts.message import AgentMessage, agent_message_as_text
from lca.contracts.protocols import TeamContext, TeamStrategy, TeamUnit
from lca.contracts.result import Result


class TeamOrchestrator(TeamUnit):
    """Holds a fully composed TeamContext + strategy. Zero mutation on agents."""

    def __init__(
        self,
        context: TeamContext,
        strategy: TeamStrategy,
    ) -> None:
        self._context = context
        self._strategy = strategy
        self.members = list(context.members)
        self.config = context.config
        self.lead = context.lead
        self.transport = context.transport
        self.teammates = list(context.teammates)
        self.team_id = context.team_id

    async def run(self, objective: str | object) -> Result:
        text = (
            agent_message_as_text(objective)
            if isinstance(objective, AgentMessage)
            else str(objective)
        )
        return await self._strategy.run(self._context, text)
