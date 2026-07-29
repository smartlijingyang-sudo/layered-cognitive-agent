"""RosterCoveragePolicy —— 基于角色覆盖率的确定性收尾策略。

纯规则判断，不调用 LLM，零额外延迟、零不确定性。
当 LLM 候选 respond 但尚有必需角色未被咨询时，强制改写为 delegate。
"""

from __future__ import annotations

import uuid

from lca.contracts.decision import DelegationSpec, StructuredDecision
from lca.contracts.enums import ActionType
from lca.contracts.protocols import CompletionPolicy
from lca.contracts.state import TypedState


def _infer_subtask(task: str, role: str) -> str:
    """从任务描述和目标角色推断子任务文本。"""
    return f"请从 {role} 的视角，针对以下任务提供你的专业意见：{task}"


class RosterCoveragePolicy(CompletionPolicy):
    """确保所有必需角色都被咨询后才允许 respond。

    判定逻辑：
    - 候选 action_type == "respond" 且 ledger 未全覆盖 → 改写为 delegate
    - 其它情况 → 原样放行
    """

    async def enforce(
        self,
        state: TypedState,
        decision: StructuredDecision,
    ) -> StructuredDecision:
        ledger = state.team_progress
        if ledger is None:
            return decision

        if decision.action_type == ActionType.RESPOND and not ledger.is_covered():
            pending = ledger.pending_roles()
            next_role = pending[0]
            return StructuredDecision(
                decision_id=f"dec_{uuid.uuid4().hex[:12]}",
                action_type=ActionType.DELEGATE,
                delegate_to=DelegationSpec(
                    target_role=next_role,
                    subtask=_infer_subtask(state.task, next_role),
                ),
                rationale="[框架强制] 尚有必需角色未咨询，禁止提前收尾",
                confidence=1.0,
            )

        return decision
