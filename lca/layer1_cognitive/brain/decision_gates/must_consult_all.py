"""MustConsultAllMembers — force consulting every required member before respond."""

from __future__ import annotations

import uuid

from lca.contracts.decision import Decision, DelegationSpec
from lca.contracts.enums import ActionType
from lca.contracts.protocols import DecisionGate
from lca.contracts.state import AgentState


def _infer_subtask(task: str, role: str) -> str:
    return f"请从 {role} 的视角，针对以下任务提供你的专业意见：{task}"


class MustConsultAllMembers(DecisionGate):
    """Rewrite early respond into delegate until all required roles are done."""

    async def enforce(
        self,
        state: AgentState,
        decision: Decision,
    ) -> Decision:
        board = state.member_status
        if board is None:
            return decision

        if decision.action_type == ActionType.RESPOND and not board.all_done():
            waiting = board.waiting_roles()
            next_role = waiting[0]
            return Decision(
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
