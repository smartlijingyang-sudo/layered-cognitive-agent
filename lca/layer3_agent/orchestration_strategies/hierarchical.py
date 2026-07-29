"""HierarchicalStrategy —— Supervisor 单向委派、汇总。
L3 层职责：
    Hierarchical 是最常用的团队编排模式：
    1. Supervisor 分析任务，拆解为子任务并委派给成员
    2. 成员独立执行，通过 DelegationLedger 跟踪进度
    3. Supervisor 汇总成员结果，生成最终输出
    自动装配 CompletionPolicy guardrail（roster_coverage），
    确保所有必选角色都完成委派后才结束。
"""

from __future__ import annotations

from typing import cast

from lca.contracts.enums import CompletionPolicyName, HookEvent
from lca.contracts.protocols import OrchestrationContext, OrchestrationStrategy
from lca.contracts.result import Result
from lca.contracts.team_progress import DelegationLedgerProtocol
from lca.layer1_cognitive.team_progress.hooks import (
    ledger_tracking_hook,
    progress_injection_hook,
)


def _default_ledger_factory(roles: frozenset[str]) -> DelegationLedgerProtocol:
    """从全局注册表解析 DelegationLedger 并实例化。"""
    from lca.layer0_infra.component_registry import get_global_registry

    reg = get_global_registry()
    ledger_cls = reg.resolve("delegation_ledger", "default")
    if ledger_cls is None:
        raise ValueError("未注册 delegation_ledger 'default'，请在 register_defaults() 后使用")
    return cast("DelegationLedgerProtocol", ledger_cls(mandatory_roles=roles))


class HierarchicalStrategy(OrchestrationStrategy):
    """Supervisor 单向委派、汇总。
    自动装配 CompletionPolicy guardrail：
    1. 通过 ledger_factory 创建 DelegationLedger（所有成员角色 → pending）
    2. 委托 supervisor.install_completion_guard 安装 guardrail
       （具体装饰器实现留在 L1，本层只表达"用哪个 policy"这一意图）
    3. 注册 post_act 记账 hook + pre_think 进度注入 hook
    """

    async def run(self, context: OrchestrationContext, objective: str) -> Result:
        if context.supervisor is None:
            raise ValueError("Hierarchical 模式需要 Supervisor")
        # ── 装配确定性收尾 guardrail ──
        mandatory_roles = frozenset(m.role_profile.role for m in context.members)
        factory = context.ledger_factory or _default_ledger_factory
        ledger = factory(mandatory_roles)
        # 解析 CompletionPolicy（默认 roster_coverage）
        policy_name = CompletionPolicyName.ROSTER_COVERAGE
        if context.config is not None:
            policy_name = context.config.completion_policy
        if policy_name != CompletionPolicyName.NONE:
            from lca.layer0_infra.component_registry import get_global_registry

            reg = get_global_registry()
            policy_factory = reg.resolve("completion_policy", policy_name)
            if policy_factory is None:
                raise ValueError(
                    f"未注册的 completion_policy: {policy_name!r}，"
                    f"可用: {reg.list('completion_policy')}"
                )
            policy = policy_factory()
            context.supervisor.install_completion_guard(policy)
            context.supervisor.register_hook(HookEvent.POST_ACT, ledger_tracking_hook)
            context.supervisor.register_hook(HookEvent.PRE_THINK, progress_injection_hook)
        return await context.supervisor.execute(objective, team_progress=ledger)
