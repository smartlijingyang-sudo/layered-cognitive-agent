"""Supervisor —— 本质上是 BaseAgent，专责任务拆解与路由。"""

from __future__ import annotations

from lca.contracts.protocols import AgentTransport, Runtime
from lca.contracts.role_team import RoleProfile
from lca.layer3_agent.base_agent import BaseAgent


class Supervisor(BaseAgent):
    """
    Supervisor 本身就是一个 BaseAgent（复用同一套认知闭环），
    区别是其 StructuredDecision 里携带 delegate_to（DelegationSpec）。
    """

    def __init__(self, runtime: Runtime, role_profile: RoleProfile, max_steps: int = 20):
        super().__init__(runtime, role_profile, max_steps=max_steps)

    def bind_team(self, transport: AgentTransport, roster_desc: str) -> None:
        """团队组建完成后的最后一次接线。

        把 transport 后置绑定到 Body（delegate 分支由此可用），
        把 roster_desc 注入 Reasoner（Supervisor prompt 里看到队友列表）。
        """
        body = self.runtime.body  # type: ignore[attr-defined]
        if hasattr(body, "transport"):
            body.transport = transport

        brain = self.runtime.brain  # type: ignore[attr-defined]
        reasoner = getattr(brain, "reasoner", None)
        if reasoner is not None:
            reasoner.team_roster = roster_desc
