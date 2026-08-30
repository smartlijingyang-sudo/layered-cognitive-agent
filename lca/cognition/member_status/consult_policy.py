"""ConsultPolicy — 证据驱动的咨询下一步（ADR-0049）。

取代「attempts++ 后原样 fan-out」：根据最近 ConsultationOutcome 决定
重试 / 终态 / 收口，并附带本轮 DelegationBudget 切片。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from lca.contracts.atoms.enums import RoleStatus
from lca.contracts.atoms.ids import elapsed_seconds
from lca.contracts.models.core.budget import (
    DEFAULT_DELEGATION_TIMEOUT_S,
    DEFAULT_MIN_USABLE_PARTIAL_CHARS,
    DelegationBudget,
)
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.team.consultation import (
    ConsultationDisposition,
    ConsultationOutcome,
    SynthesisMethod,
    latest_outcome_for_role,
    usable_outcomes,
)
from lca.contracts.models.team.member_status import MemberStatus
from lca.contracts.models.team.role_status_rules import (
    is_full_success_status,
    is_success_status,
    is_terminal_status,
)
from lca.contracts.models.team.team_awareness import ConsultDuty


@dataclass(frozen=True)
class ConsultNextAction:
    """状态机允许的下一步咨询动作。"""

    kind: Literal["must_consult", "may_respond"]
    target_roles: tuple[str, ...] = ()
    mode: Literal["initial_fanout", "retry_empty", "force_respond"] = "initial_fanout"
    budget: DelegationBudget = field(default_factory=DelegationBudget)
    synthesis_method: SynthesisMethod | None = None


def run_wall_clock_remaining_s(budget: Budget) -> float | None:
    """父 run 剩余墙钟秒数；无墙钟上限时返回 None。"""
    if budget.max_wall_clock_seconds is None:
        return None
    remaining = float(budget.max_wall_clock_seconds) - elapsed_seconds(budget.started_at)
    return remaining


def delegation_budget_for_state(
    state: AgentState,
    *,
    max_attempts: int,
    min_usable_partial_chars: int = DEFAULT_MIN_USABLE_PARTIAL_CHARS,
    default_timeout_s: float = DEFAULT_DELEGATION_TIMEOUT_S,
) -> DelegationBudget:
    """从 AgentState.budget 派生本轮 DelegationBudget。"""
    remaining = run_wall_clock_remaining_s(state.budget)
    if remaining is None:
        timeout_s = default_timeout_s
    else:
        timeout_s = max(0.0, min(default_timeout_s, remaining))
    return DelegationBudget(
        timeout_s=timeout_s,
        max_attempts=max_attempts,
        min_usable_partial_chars=min_usable_partial_chars,
    )


def classify_synthesis(board: MemberStatus, outcomes: list[ConsultationOutcome]) -> SynthesisMethod:
    """按证据完备度命名收口方法。"""
    usable = usable_outcomes(outcomes)
    if not usable:
        return SynthesisMethod.SOLO_FALLBACK
    required = board.required_roles
    full_roles = {
        r for r in required if is_full_success_status(board.status.get(r, RoleStatus.PENDING))
    }
    if full_roles == set(required) and len(usable) >= len(required):
        return SynthesisMethod.FULL
    return SynthesisMethod.PARTIAL


def compute_consult_next(duty: ConsultDuty, state: AgentState) -> ConsultNextAction:
    """证据驱动的下一步：只对「仍 waiting 且应重试」的角色 fan-out。"""
    board = duty.member_status
    budget = delegation_budget_for_state(
        state,
        max_attempts=duty.max_attempts,
        min_usable_partial_chars=duty.min_usable_partial_chars,
    )
    waiting = [r for r in board.waiting_roles() if _should_retry(duty, r)]
    if not waiting:
        # 仍有 non-terminal 但不该重试 → 视为可收口（防御）
        method = classify_synthesis(board, duty.outcomes)
        return ConsultNextAction(
            kind="may_respond",
            mode="force_respond",
            budget=budget,
            synthesis_method=method,
        )
    # 区分首轮与空超时重试
    any_prior = any(latest_outcome_for_role(duty.outcomes, r) is not None for r in waiting)
    mode: Literal["initial_fanout", "retry_empty"] = (
        "retry_empty" if any_prior else "initial_fanout"
    )
    return ConsultNextAction(
        kind="must_consult",
        target_roles=tuple(waiting),
        mode=mode,
        budget=budget,
        synthesis_method=None,
    )


def _should_retry(duty: ConsultDuty, role: str) -> bool:
    if is_terminal_status(duty.member_status.status.get(role, RoleStatus.PENDING)):
        return False
    attempts = duty.attempts.get(role, 0)
    if attempts >= duty.max_attempts:
        return False
    last = latest_outcome_for_role(duty.outcomes, role)
    if last is None:
        return True
    # 已有 usable 证据不应再问（状态板应已 terminal；此处双保险）
    if last.usable:
        return False
    # 仅 empty timeout / transient error 可重试
    if last.disposition in (
        ConsultationDisposition.TIMEOUT,
        ConsultationDisposition.ERROR,
    ):
        return attempts < duty.max_attempts
    return False


def _terminalize_non_retriable(duty: ConsultDuty) -> None:
    """将「不应再试但仍 PENDING」的角色标 FAILED，保证门闩与证据一致。"""
    board = duty.member_status
    for role in list(board.waiting_roles()):
        if _should_retry(duty, role):
            continue
        board = board.mark(role, RoleStatus.FAILED)
    duty.member_status = board


def compute_required_action_from_duty(duty: ConsultDuty, state: AgentState) -> ConsultNextAction:
    """对外主入口（gate / respond 共用）。"""
    _terminalize_non_retriable(duty)
    board = duty.member_status
    if board.all_terminal() or not board.waiting_roles():
        method = classify_synthesis(board, duty.outcomes)
        budget = delegation_budget_for_state(
            state,
            max_attempts=duty.max_attempts,
            min_usable_partial_chars=duty.min_usable_partial_chars,
        )
        return ConsultNextAction(
            kind="may_respond",
            mode="force_respond",
            budget=budget,
            synthesis_method=method,
        )
    return compute_consult_next(duty, state)


def evidence_coverage_summary(duty: ConsultDuty) -> str:
    """MEMBER_STATUS 旁路：证据覆盖摘要。"""
    parts: list[str] = []
    order = getattr(duty.member_status, "role_order", None)
    roles = list(order) if order is not None else sorted(duty.member_status.required_roles)
    for role in roles:
        st = duty.member_status.status.get(role, RoleStatus.PENDING)
        last = latest_outcome_for_role(duty.outcomes, role)
        if is_full_success_status(st):
            parts.append(f"{role}=完整证据")
        elif is_success_status(st):
            parts.append(f"{role}=部分证据")
        elif st == RoleStatus.FAILED:
            reason = (last.error if last else None) or "不可用"
            parts.append(f"{role}=失败({reason})")
        else:
            parts.append(f"{role}=待咨询")
    return "；".join(parts)
