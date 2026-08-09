"""MustConsultAllMembers — force consulting every required member before respond.

ADR-0049：短路与强制改写均挂载 DelegationBudget（timeout_s），
并按 ConsultPolicy 只 fan-out「仍应咨询」的角色（usable partial 不再重试）。
"""

from __future__ import annotations

from lca.contracts.atoms.enums import ActionType
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.decision import Decision, DelegationSpec
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import DecisionGate
from lca.layer1_cognitive.member_status.consult_policy import (
    ConsultNextAction,
    compute_required_action_from_duty,
)
from lca.layer1_cognitive.member_status.required_action import compute_required_action
from lca.layer1_cognitive.member_status.tracking import duty_board, duty_consult

_CONSULT_SUBTASK_TEMPLATE = "请从 {role} 的视角，针对以下任务提供你的专业意见：{task}"
_RATIONALE_SHORTCUT_SINGLE = "[框架短路] 唯一待咨询角色已确定，跳过本轮 LLM 调用"
_RATIONALE_SHORTCUT_MULTI = "[框架短路] 并行咨询待咨询角色，跳过本轮 LLM 调用"
_RATIONALE_FORCE_MULTI = "[框架强制] 尚有必需角色未回复,并行委派仍待咨询角色"
_RATIONALE_FORCE_SINGLE = "[框架强制] 尚有必需角色未回复,禁止提前收尾或委派已终态角色"
_RATIONALE_FORCE_RESPOND = "[框架强制] 所有必需角色均已终态,无需进一步委派"


def _infer_subtask(task: str, role: str) -> str:
    return _CONSULT_SUBTASK_TEMPLATE.format(role=role, task=task)


def _delegate_decision(
    task: str,
    roles: list[str],
    *,
    rationale: str,
    timeout_s: float,
) -> Decision:
    specs = [
        DelegationSpec(
            target_role=role,
            subtask=_infer_subtask(task, role),
            timeout_s=timeout_s,
        )
        for role in roles
    ]
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


def _next_from_state(state: AgentState) -> ConsultNextAction | None:
    duty = duty_consult(state)
    if duty is None:
        return None
    return compute_required_action_from_duty(duty, state)


class MustConsultAllMembers(DecisionGate):
    """Rewrite decisions that violate the "all required roles must respond" invariant.

    With multi-delegate support: when multiple roles are waiting, a DELEGATE
    whose targets are a non-empty subset of waiting is accepted; shortcut may
    fan-out to **policy-selected** waiting roles in one step (not blind retry).
    """

    async def try_shortcut(self, state: AgentState) -> Decision | None:
        nxt = _next_from_state(state)
        if nxt is None or nxt.kind != "must_consult" or not nxt.target_roles:
            return None
        roles = list(nxt.target_roles)
        rationale = _RATIONALE_SHORTCUT_SINGLE if len(roles) == 1 else _RATIONALE_SHORTCUT_MULTI
        return _delegate_decision(
            state.task,
            roles,
            rationale=rationale,
            timeout_s=nxt.budget.timeout_s,
        )

    async def enforce(
        self,
        state: AgentState,
        decision: Decision,
    ) -> Decision:
        duty = duty_consult(state)
        if duty is None:
            board = duty_board(state)
            if board is None:
                return decision
            # 无 duty 对象时退回旧 board 逻辑
            required = compute_required_action(board)
            if required.kind == "may_respond":
                if decision.action_type == ActionType.DELEGATE:
                    return _respond_override(_RATIONALE_FORCE_RESPOND)
                return decision
            roles = list(required.target_roles) or (
                [required.target_role] if required.target_role else []
            )
            return _delegate_decision(
                state.task,
                roles,
                rationale=_RATIONALE_FORCE_MULTI if len(roles) > 1 else _RATIONALE_FORCE_SINGLE,
                timeout_s=300.0,
            )

        nxt = compute_required_action_from_duty(duty, state)
        if nxt.kind == "may_respond":
            if decision.action_type == ActionType.DELEGATE:
                return _respond_override(_RATIONALE_FORCE_RESPOND)
            return decision

        if decision.action_type not in (ActionType.RESPOND, ActionType.DELEGATE):
            return decision

        waiting_set = set(nxt.target_roles)
        specs = list(decision.delegations)
        target_roles = {s.target_role for s in specs if s.target_role}
        already_correct = (
            decision.action_type == ActionType.DELEGATE
            and bool(target_roles)
            and target_roles.issubset(waiting_set)
        )
        if already_correct:
            # 补齐缺失的 timeout_s
            patched: list[DelegationSpec] = []
            for spec in specs:
                if spec.timeout_s is None:
                    patched.append(
                        DelegationSpec(
                            subtask=spec.subtask,
                            target_role=spec.target_role,
                            target_agent_id=spec.target_agent_id,
                            target_agent_card=spec.target_agent_card,
                            context_refs=list(spec.context_refs),
                            deadline=spec.deadline,
                            timeout_s=nxt.budget.timeout_s,
                            protocol=spec.protocol,
                        )
                    )
                else:
                    patched.append(spec)
            decision.delegations = patched
            return decision

        roles = list(nxt.target_roles)
        rationale = _RATIONALE_FORCE_MULTI if len(roles) > 1 else _RATIONALE_FORCE_SINGLE
        return _delegate_decision(
            state.task,
            roles,
            rationale=rationale,
            timeout_s=nxt.budget.timeout_s,
        )
