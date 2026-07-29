"""Supervisor —— 本质上是 BaseAgent，专责任务拆解与路由。"""

from __future__ import annotations

from collections.abc import Callable

from lca.contracts.mechanisms import Hook
from lca.contracts.protocols import CandidateEvaluationPipeline
from lca.contracts.role_team import RoleProfile
from lca.layer3_agent.base_agent import BaseAgent


class Supervisor(BaseAgent):
    """
    Supervisor 本身就是一个 BaseAgent（复用同一套认知闭环），
    区别是其 StructuredDecision 里携带 delegate_to（DelegationSpec）。
    """

    def __init__(
        self,
        runtime: object,
        role_profile: RoleProfile,
        max_steps: int = 20,
        max_wall_clock_seconds: int | None = 300,
    ):
        super().__init__(
            runtime,  # type: ignore[arg-type]
            role_profile,
            max_steps=max_steps,
            max_wall_clock_seconds=max_wall_clock_seconds,
        )

    def register_hook(self, hook_name: str, hook_fn: Hook) -> None:
        """注册 Hook 到 Runtime 的 HookRegistry。"""
        hooks = getattr(self.runtime, "hooks", None)
        if hooks is not None:
            hooks.register(hook_name, hook_fn)

    def wrap_evaluation_pipeline(
        self,
        wrapper: Callable[[CandidateEvaluationPipeline], CandidateEvaluationPipeline],
    ) -> None:
        """通过 Runtime 协议装饰 Brain 内部评估管线。"""
        self.runtime.wrap_evaluation_pipeline(wrapper)
