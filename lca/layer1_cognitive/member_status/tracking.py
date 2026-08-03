"""Member-status tracking — direct state update after DELEGATE settles.

Retry classification is pure; board mutation lives on ConsultationState.
"""

from __future__ import annotations

from lca.contracts.decision import Decision, DelegationSpec, Observation
from lca.contracts.enums import RoleStatus
from lca.contracts.semantic_keys import (
    FAILURE_KIND,
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_VALIDATION,
)
from lca.contracts.state import AgentState


def _next_role_status(
    *,
    success: bool,
    failure_kind: str,
    attempts_after: int,
    max_attempts: int,
) -> RoleStatus:
    """Pure classifier: no AgentState/Board access."""
    if success:
        return RoleStatus.DONE
    if failure_kind == FAILURE_KIND_VALIDATION:
        return RoleStatus.FAILED
    if attempts_after >= max_attempts:
        return RoleStatus.FAILED
    return RoleStatus.PENDING


def update_member_status_for_spec(
    state: AgentState, spec: DelegationSpec, observation: Observation
) -> None:
    """Update the consultation board for one delegation target."""
    consultation = state.consultation
    if consultation is None:
        return
    board = consultation.member_status
    role = spec.target_role
    if role is None or role not in board.required_roles:
        return

    if observation.success:
        consultation.member_status = board.mark(role, RoleStatus.DONE)
        return

    failure_kind = observation.extra.get(FAILURE_KIND, FAILURE_KIND_EXECUTION)
    attempts_after = consultation.delegate_attempts.get(role, 0) + 1
    consultation.delegate_attempts[role] = attempts_after

    new_status = _next_role_status(
        success=False,
        failure_kind=failure_kind,
        attempts_after=attempts_after,
        max_attempts=consultation.delegate_max_attempts,
    )
    consultation.member_status = board.mark(role, new_status)


def update_member_status(state: AgentState, decision: Decision, observation: Observation) -> None:
    """Update the consultation board after a single-target DELEGATE completes."""
    specs = list(decision.delegations)
    if len(specs) != 1:
        return
    update_member_status_for_spec(state, specs[0], observation)


def record_routing_assignment(state: AgentState, spec: DelegationSpec) -> None:
    """Soft-log assigned role on free routing plane (advisory only)."""
    routing = state.routing
    if routing is None or not spec.target_role:
        return
    if spec.target_role not in routing.assigned_roles:
        routing.assigned_roles.append(spec.target_role)
