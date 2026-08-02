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


def _delegate_decision(task: str, role: str, *, rationale: str) -> Decision:
    return Decision(
        decision_id=new_id("dec"),
        action_type=ActionType.DELEGATE,
        delegate_to=DelegationSpec(target_role=role, subtask=_infer_subtask(task, role)),
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

    Implements ``DecisionGate.enforce`` (required) and structurally satisfies
    ``SupportsShortcut.try_shortcut`` (optional — not declared as a base class,
    same convention as ``SimpleBody`` satisfying ``HasChannel``).

    ``try_shortcut`` only short-circuits when exactly one required role is still
    waiting: the one case where ``compute_required_action()``'s outcome cannot
    change no matter what the LLM says, so asking it is pure waste. Two or
    more waiting roles is left to the cognitive pipeline — which role to
    consult next, and how to phrase the ask, is genuine LLM discretion that
    ``enforce`` below already knows how to validate after the fact.

    ``enforce`` is unchanged in behavior from before try_shortcut existed: it
    remains the single correctness backstop regardless of whether try_shortcut
    ran, fired, or exists at all on some other DecisionGate.

    Scope: only RESPOND and DELEGATE are intercepted. HANDOFF / USE_TOOL
    pass through unchanged. Extending gate jurisdiction is an explicit
    product decision, declared out-of-scope in ADR-0025.
    """

    async def try_shortcut(self, state: AgentState) -> Decision | None:
        board = state.member_status
        if board is None:
            return None
        waiting = board.waiting_roles()
        if len(waiting) != 1:
            return None
        return _delegate_decision(
            state.task,
            waiting[0],
            rationale="[框架短路] 唯一待咨询角色已确定，跳过本轮 LLM 调用",
        )

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
                return _respond_override("[框架强制] 所有必需角色已结算,无需进一步委派")
            return decision

        # required.kind == "must_delegate"; try_shortcut already short-circuits
        # len(waiting) == 1, so reaching here means >= 2 waiting roles.
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
        return _delegate_decision(
            state.task,
            target,
            rationale="[框架强制] 尚有必需角色未完成结算,禁止提前收尾或委派已终态角色",
        )
