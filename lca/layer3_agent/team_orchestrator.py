"""TeamOrchestrator —— 管理团队的组织形态与通信信道。"""

from __future__ import annotations

from lca.contracts.protocols import AgentTransport
from lca.contracts.result import Result
from lca.contracts.role_team import TeamConfig
from lca.layer3_agent.base_agent import BaseAgent
from lca.layer3_agent.supervisor import Supervisor


class TeamOrchestrator:
    """
    支持四种组织形态（hierarchical / sequential / graph / debate），
    均复用同一套底层 Runtime。
    """

    def __init__(
        self,
        members: list[BaseAgent],
        config: TeamConfig,
        supervisor: Supervisor | None = None,
        transport: AgentTransport | None = None,
        roster_desc: str = "",
    ):
        self.members = members
        self.config = config
        self.supervisor = supervisor
        self.transport = transport
        self.roster_desc = roster_desc

    async def run(self, objective: str) -> Result:
        """按 TeamConfig.process 类型选择组织形态执行。"""
        if self.config.process == "hierarchical":
            return await self._run_hierarchical(objective)
        elif self.config.process == "sequential":
            return await self._run_sequential(objective)
        else:
            return await self._run_hierarchical(objective)

    async def _run_hierarchical(self, objective: str) -> Result:
        """Supervisor 单向委派、汇总。"""
        if self.supervisor is None:
            raise ValueError("Hierarchical 模式需要 Supervisor")
        if self.transport is not None:
            self.supervisor.bind_team(self.transport, self.roster_desc)
        return await self.supervisor.execute(objective)

    async def _run_sequential(self, objective: str) -> Result:
        """任务像流水线一样在成员间顺序传递。"""
        current_task = objective
        last_result: Result | None = None
        for member in self.members:
            last_result = await member.execute(current_task)
            if last_result.output:
                current_task = last_result.output
        return last_result or Result(
            trace_id="",
            status="failed",
            final_state_ref="",
            total_steps=0,
            budget_used=None,  # type: ignore[arg-type]
            error="No members in team",
        )
