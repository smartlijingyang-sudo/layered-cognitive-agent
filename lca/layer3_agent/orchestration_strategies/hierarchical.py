"""HierarchicalStrategy —— Supervisor 单向委派、汇总。

L3 层职责：
    Hierarchical 是最常用的团队编排模式：
    1. Supervisor 分析任务，拆解为子任务并委派给成员
    2. 成员独立执行，通过 DelegationLedger 跟踪进度
    3. Supervisor 汇总成员结果，生成最终输出

    所有组合期绑定（ledger 创建、hooks 注册、completion guard 安装）
    由 TeamOrchestrator 在构造时完成，本策略只负责调用 execute。
"""

from __future__ import annotations

from lca.contracts.protocols import OrchestrationContext, OrchestrationStrategy
from lca.contracts.result import Result


class HierarchicalStrategy(OrchestrationStrategy):
    """Supervisor 单向委派、汇总。

    组合期已由 TeamOrchestrator 完成：
    - DelegationLedger 创建（所有成员角色 → pending）
    - POST_ACT ledger_tracking_hook（记账）
    - PRE_THINK progress_injection_hook（进度注入）
    - CompletionPolicy guard（roster_coverage 确定性收尾）

    本策略只需将 objective + ledger 交给 supervisor.execute。
    """

    async def run(self, context: OrchestrationContext, objective: str) -> Result:
        if context.supervisor is None:
            raise ValueError("Hierarchical 模式需要 Supervisor")
        return await context.supervisor.execute(objective, team_progress=context.team_progress)
