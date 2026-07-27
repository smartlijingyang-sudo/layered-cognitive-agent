"""TeamOrchestrator —— 管理团队的组织形态与通信信道。"""

from __future__ import annotations

from lca.contracts.protocols import (
    AgentTransport,
    OrchestrationContext,
    OrchestrationStrategy,
)
from lca.contracts.result import Result
from lca.contracts.role_team import TeamConfig
from lca.layer3_agent.base_agent import BaseAgent
from lca.layer3_agent.orchestration_registry import get_global_orchestration_registry
from lca.layer3_agent.supervisor import Supervisor


class TeamOrchestrator:
    """
    支持四种组织形态（hierarchical / sequential / graph / debate），
    通过 OrchestrationStrategyRegistry 解析策略，不再 if/elif 硬编码。
    """

    def __init__(
        self,
        members: list[BaseAgent],
        config: TeamConfig,
        supervisor: Supervisor | None = None,
        transport: AgentTransport | None = None,
        roster_desc: str = "",
        strategy: OrchestrationStrategy | None = None,
    ):
        self.members = members
        self.config = config
        self.supervisor = supervisor
        self.transport = transport
        self.roster_desc = roster_desc

        if strategy is not None:
            self._strategy = strategy
        else:
            registry = get_global_orchestration_registry()
            self._strategy = registry.resolve(config.process)

        self._context = OrchestrationContext(
            members=members,
            config=config,
            supervisor=supervisor,
            transport=transport,
            roster_desc=roster_desc,
        )

    async def run(self, objective: str) -> Result:
        """按 TeamConfig.process 类型选择组织形态执行。"""
        return await self._strategy.run(self._context, objective)
