"""BaseAgent —— 持有 Runtime + Brain + Body + Memory 视图。"""

from __future__ import annotations

from contracts.role_team import RoleProfile
from contracts.result import Result
from contracts.protocols import Runtime, AgentProtocol


class BaseAgent(AgentProtocol):
    """单个 Agent 的运行时封装。"""

    def __init__(self, runtime: Runtime, role_profile: RoleProfile, max_steps: int = 10):
        self.runtime = runtime
        self.role_profile = role_profile
        self.max_steps = max_steps

    async def execute(self, task: str) -> Result:
        return await self.runtime.run(task, max_steps=self.max_steps)
