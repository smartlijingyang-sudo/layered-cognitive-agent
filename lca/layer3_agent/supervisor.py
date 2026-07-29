"""Supervisor —— 本质上是 BaseAgent，专责任务拆解与路由。"""

from __future__ import annotations

from typing import Any

from lca.contracts.protocols import AgentTransport, Runtime
from lca.contracts.role_team import RoleProfile
from lca.layer3_agent.base_agent import BaseAgent


class Supervisor(BaseAgent):
    """
    Supervisor 本身就是一个 BaseAgent（复用同一套认知闭环），
    区别是其 StructuredDecision 里携带 delegate_to（DelegationSpec）。
    """

    def __init__(
        self,
        runtime: Runtime,
        role_profile: RoleProfile,
        max_steps: int = 20,
        max_wall_clock_seconds: int | None = 300,
    ):
        super().__init__(
            runtime,
            role_profile,
            max_steps=max_steps,
            max_wall_clock_seconds=max_wall_clock_seconds,
        )

    def bind_team(self, transport: AgentTransport, roster_desc: str) -> None:
        """团队组建完成后的最后一次接线。

        通过 Runtime.configure() 显式协议分发能力，
        不再越层访问 L1 组件内部状态。
        """
        self.runtime.configure(transport=transport, team_roster=roster_desc)

    def configure_runtime(self, **capabilities: Any) -> None:
        """通过 Runtime 协议配置能力（team_progress 等）。"""
        self.runtime.configure(**capabilities)

    def register_hook(self, hook_name: str, hook_fn: Any) -> None:
        """通过 Runtime 协议注册 Hook。"""
        self.runtime.register_hook(hook_name, hook_fn)

    def wrap_brain_component(self, name: str, wrapper: Any) -> None:
        """通过 Runtime 协议包装 Brain 的指定组件（装饰器模式）。"""
        self.runtime.wrap_brain_component(name, wrapper)
