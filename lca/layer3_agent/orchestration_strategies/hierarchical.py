"""HierarchicalStrategy —— Supervisor 单向委派、汇总。"""

from __future__ import annotations

from typing import cast

from lca.contracts.protocols import OrchestrationContext, OrchestrationStrategy
from lca.contracts.result import Result
from lca.contracts.team_progress import (
    DelegationLedger,
    ledger_tracking_hook,
    progress_injection_hook,
)


class HierarchicalStrategy(OrchestrationStrategy):
    """Supervisor 单向委派、汇总。

    自动装配 CompletionPolicy guardrail：
    1. 初始化 DelegationLedger（所有成员角色 → pending）
    2. 用 GuardedTaskCoordinator 包装 supervisor 的 task_coordinator
    3. 注册 post_act 记账 hook + pre_think 进度注入 hook
    """

    async def run(self, context: OrchestrationContext, objective: str) -> Result:
        if context.supervisor is None:
            raise ValueError("Hierarchical 模式需要 Supervisor")
        if context.transport is not None:
            context.supervisor.bind_team(context.transport, context.roster_desc)

        # ── 装配确定性收尾 guardrail ──
        mandatory_roles = frozenset(m.role_profile.role for m in context.members)
        ledger = DelegationLedger(
            mandatory_roles=mandatory_roles,
            status=dict.fromkeys(mandatory_roles, "pending"),
        )

        runtime = context.supervisor.runtime
        runtime.configure(team_progress=ledger)

        # 解析 CompletionPolicy（默认 roster_coverage）
        policy_name = "roster_coverage"
        if context.config is not None:
            policy_name = context.config.completion_policy

        if policy_name != "none":
            from lca.layer0_infra.registry import get_global_registry
            from lca.layer1_cognitive.brain.guarded_coordinator import (
                GuardedTaskCoordinator,
            )

            reg = get_global_registry()
            policy_factory = reg.resolve("completion_policy", policy_name)
            if policy_factory is None:
                raise ValueError(
                    f"未注册的 completion_policy: {policy_name!r}，"
                    f"可用: {reg.list('completion_policy')}"
                )
            policy = policy_factory()

            brain = runtime.brain
            if hasattr(brain, "task_coordinator"):
                brain.task_coordinator = GuardedTaskCoordinator(brain.task_coordinator, policy)

            # 注册 ledger 记账 hook（post_act）和进度注入 hook（pre_think）
            runtime.hooks.register("post_act", ledger_tracking_hook)
            runtime.hooks.register("pre_think", progress_injection_hook)

        return cast("Result", await context.supervisor.execute(objective))
