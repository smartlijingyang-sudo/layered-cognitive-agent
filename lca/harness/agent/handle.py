"""Owner-only handle around a LiveAgent."""

from __future__ import annotations

from lca.contracts.harness.collaboration.agent import LiveAgent


class OwnerAgentHandle:
    def __init__(self, agent: LiveAgent) -> None:
        self._agent = agent

    @property
    def agent(self) -> LiveAgent:
        return self._agent

    async def dispose(self, reason: str = "owner") -> None:
        await self._agent.cancel(reason)
