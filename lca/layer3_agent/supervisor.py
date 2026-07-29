"""Supervisor —— 本质上是 BaseAgent，专责任务拆解与路由。
L3 层职责：
    Supervisor 是 Hierarchical 编排模式的核心角色，
    复用 BaseAgent 的认知闭环，但通过 DelegationSpec
    将子任务分派给团队成员，最终汇总结果。
"""

from __future__ import annotations

from lca.contracts.mechanisms import Hook
from lca.contracts.protocols import CompletionPolicy, Runtime
from lca.contracts.role_team import RoleProfile
from lca.layer3_agent.base_agent import BaseAgent

_DEFAULT_SUPERVISOR_MAX_STEPS = 20
_DEFAULT_SUPERVISOR_TIMEOUT_S = 300


class Supervisor(BaseAgent):
    """Supervisor 本身就是一个 BaseAgent（复用同一套认知闭环）。
    区别是其 StructuredDecision 里携带 delegate_to（DelegationSpec），
    由 HierarchicalStrategy 装配 CompletionPolicy guardrail 后使用。
    """

    def __init__(
        self,
        runtime: Runtime,
        role_profile: RoleProfile,
        max_steps: int = _DEFAULT_SUPERVISOR_MAX_STEPS,
        max_wall_clock_seconds: int | None = _DEFAULT_SUPERVISOR_TIMEOUT_S,
    ) -> None:
        super().__init__(
            runtime,
            role_profile,
            max_steps=max_steps,
            max_wall_clock_seconds=max_wall_clock_seconds,
        )

    def register_hook(self, hook_name: str, hook_fn: Hook) -> None:
        """注册 Hook 到 Runtime 的 HookRegistry。"""
        hooks = getattr(self.runtime, "hooks", None)
        if hooks is not None:
            hooks.register(hook_name, hook_fn)

    def install_completion_guard(self, policy: CompletionPolicy) -> None:
        """通过 Runtime 协议安装确定性收尾 guardrail。"""
        self.runtime.install_completion_guard(policy)
