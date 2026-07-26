"""Supervisor —— 本质上是 BaseAgent，专责任务拆解与路由。"""

from __future__ import annotations

from lca.contracts.role_team import RoleProfile
from lca.contracts.result import Result
from lca.contracts.protocols import Runtime
from lca.layer3_agent.base_agent import BaseAgent


class Supervisor(BaseAgent):
    """
    Supervisor 本身就是一个 BaseAgent（复用同一套认知闭环），
    区别是其 StructuredDecision 里携带 delegate_to（DelegationSpec）。
    """

    def __init__(self, runtime: Runtime, role_profile: RoleProfile, max_steps: int = 20):
        super().__init__(runtime, role_profile, max_steps=max_steps)

    async def delegate(self, task: str) -> Result:
        """委派任务给子 Agent。"""
        return await self.execute(task)
