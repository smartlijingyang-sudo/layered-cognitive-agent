"""MustConsultAllMembers — force consulting every required member before respond."""

from __future__ import annotations

from lca.contracts.decision import Decision, DelegationSpec
from lca.contracts.enums import ActionType
from lca.contracts.ids import new_id
from lca.contracts.protocols import DecisionGate
from lca.contracts.state import AgentState
from lca.layer1_cognitive.member_status.policy import compute_required_action

_CONSULT_SUBTASK_TEMPLATE = "请从 {role} 的视角，针对以下任务提供你的专业意见：{task}"


def _infer_subtask(task: str, role: str) -> str:
    return _CONSULT_SUBTASK_TEMPLATE.format(role=role, task=task)


class MustConsultAllMembers(DecisionGate):
    """Rewrite decisions that violate the "all required roles must settle" invariant.

    Both directions (block premature RESPOND, block DELEGATE to already-settled
    roles) share a single ``compute_required_action()`` call — there are not two
    independent branches to drift apart.

    Scope: only RESPOND and DELEGATE are intercepted. HANDOFF / USE_TOOL
    pass through unchanged. Extending gate jurisdiction is an explicit
    product decision, declared out-of-scope in ADR-0025.
    """

    async def enforce(
        self,
        state: AgentState,
        decision: Decision,
    ) -> Decision:
        board = state.member_status
        if board is None:
            return decision

        if decision.action_type not in (ActionType.RESPOND, ActionType.DELEGATE):
            return decision

        required = compute_required_action(board)

        if required.kind == "may_respond":
            if decision.action_type == ActionType.DELEGATE:
                return Decision(
                    decision_id=new_id("dec"),
                    action_type=ActionType.RESPOND,
                    rationale="[框架强制] 所有必需角色已结算,无需进一步委派",
                    confidence=1.0,
                )
            return decision

        # required.kind == "must_delegate"
        waiting_set = set(board.waiting_roles())
        already_correct = (
            decision.action_type == ActionType.DELEGATE
            and decision.delegate_to is not None
            and decision.delegate_to.target_role in waiting_set
        )
        if already_correct:
            return decision

        target = required.target_role
        if target is None:
            return decision  # defensive: compute_required_action invariant
        return Decision(
            decision_id=new_id("dec"),
            action_type=ActionType.DELEGATE,
            delegate_to=DelegationSpec(
                target_role=target,
                subtask=_infer_subtask(state.task, target),
            ),
            rationale="[框架强制] 尚有必需角色未完成结算,禁止提前收尾或委派已终态角色",
            confidence=1.0,
        )
