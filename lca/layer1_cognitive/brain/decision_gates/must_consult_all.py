"""MustConsultAllMembers — force consulting every required member before respond."""

from __future__ import annotations

from lca.contracts.decision import Decision, DelegationSpec
from lca.contracts.enums import ActionType
from lca.contracts.ids import new_id
from lca.contracts.protocols import DecisionGate
from lca.contracts.state import AgentState
from lca.layer1_cognitive.member_status.required_action import compute_required_action

_CONSULT_SUBTASK_TEMPLATE = "请从 {role} 的视角，针对以下任务提供你的专业意见：{task}"


def _infer_subtask(task: str, role: str) -> str:
    return _CONSULT_SUBTASK_TEMPLATE.format(role=role, task=task)


def _delegate_decision(task: str, role: str, *, rationale: str) -> Decision:
    spec = DelegationSpec(target_role=role, subtask=_infer_subtask(task, role))
    return Decision(
        decision_id=new_id("dec"),
        action_type=ActionType.DELEGATE,
        delegations=[spec],
        rationale=rationale,
        confidence=1.0,
    )


def _multi_delegate_decision(task: str, roles: list[str], *, rationale: str) -> Decision:
    specs = [DelegationSpec(target_role=role, subtask=_infer_subtask(task, role)) for role in roles]
    return Decision(
        decision_id=new_id("dec"),
        action_type=ActionType.DELEGATE,
        delegations=specs,
        rationale=rationale,
        confidence=1.0,
    )


def _respond_override(rationale: str) -> Decision:
    return Decision(
        decision_id=new_id("dec"),
        action_type=ActionType.RESPOND,
        rationale=rationale,
        confidence=1.0,
    )


class MustConsultAllMembers(DecisionGate):
    """Rewrite decisions that violate the "all required roles must settle" invariant.

    With multi-delegate support: when multiple roles are waiting, a DELEGATE
    whose targets are a non-empty subset of waiting is accepted; shortcut may
    fan-out to **all** waiting roles in one step.
    """

    async def try_shortcut(self, state: AgentState) -> Decision | None:
        from lca.contracts.session import as_consultation

        consultation = as_consultation(state.session)
        board = consultation.member_status if consultation else None
        if board is None:
            return None
        waiting = board.waiting_roles()
        if not waiting:
            return None
        if len(waiting) == 1:
            return _delegate_decision(
                state.task,
                waiting[0],
                rationale="[框架短路] 唯一待咨询角色已确定，跳过本轮 LLM 调用",
            )
        return _multi_delegate_decision(
            state.task,
            waiting,
            rationale="[框架短路] 并行咨询全部待结算角色，跳过本轮 LLM 调用",
        )

    async def enforce(
        self,
        state: AgentState,
        decision: Decision,
    ) -> Decision:
        from lca.contracts.session import as_consultation

        consultation = as_consultation(state.session)
        board = consultation.member_status if consultation else None
        if board is None:
            return decision

        if decision.action_type not in (ActionType.RESPOND, ActionType.DELEGATE):
            return decision

        required = compute_required_action(board)

        if required.kind == "may_respond":
            if decision.action_type == ActionType.DELEGATE:
                return _respond_override("[框架强制] 所有必需角色已结算,无需进一步委派")
            return decision

        waiting_set = set(board.waiting_roles())
        specs = list(decision.delegations)
        target_roles = {s.target_role for s in specs if s.target_role}
        already_correct = (
            decision.action_type == ActionType.DELEGATE
            and bool(target_roles)
            and target_roles.issubset(waiting_set)
        )
        if already_correct:
            return decision

        if len(waiting_set) > 1:
            return _multi_delegate_decision(
                state.task,
                board.waiting_roles(),
                rationale="[框架强制] 尚有必需角色未完成结算,并行委派全部等待角色",
            )
        target = required.target_role
        if target is None:
            return decision
        return _delegate_decision(
            state.task,
            target,
            rationale="[框架强制] 尚有必需角色未完成结算,禁止提前收尾或委派已终态角色",
        )
