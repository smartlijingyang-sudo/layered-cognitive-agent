"""Member-status tracking — direct state update after DELEGATE settles.

Retry classification is pure; board mutation lives on ConsultationState.
"""

from __future__ import annotations

from lca.contracts.decision import Decision, DelegationSpec, Observation
from lca.contracts.delegation import DelegationResult
from lca.contracts.enums import RoleStatus
from lca.contracts.ids import new_id, utc_now
from lca.contracts.semantic_keys import (
    FAILURE_KIND,
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_VALIDATION,
    OBS_TASK_ID,
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
    from lca.contracts.session import as_consultation

    consultation = as_consultation(state.session)
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
    from lca.contracts.session import as_routing

    routing = as_routing(state.session)
    if routing is None or not spec.target_role:
        return
    if spec.target_role not in routing.assigned_roles:
        routing.assigned_roles.append(spec.target_role)


def record_routing_result(
    state: AgentState, spec: DelegationSpec, observation: Observation
) -> None:
    """Append a settled delegation to the routing ledger.

    The ledger is the authoritative fact source for the supervisor prompt
    (MEMBER_REPORTS) and idempotent delegation. Failed settlements are
    recorded too so the prompt can surface "who has not answered yet";
    ``find_result`` only matches successful ones.
    """
    from lca.contracts.session import as_routing

    routing = as_routing(state.session)
    if routing is None or not spec.target_role:
        return
    task_id = observation.extra.get(OBS_TASK_ID)
    output = observation.payload if observation.success else None
    routing.results.append(
        DelegationResult(
            result_id=new_id("dres"),
            target_role=spec.target_role,
            subtask=spec.subtask,
            output=str(output) if output is not None else None,
            success=observation.success,
            error=observation.error,
            task_id=str(task_id) if task_id is not None else None,
            step=state.step,
            returned_at=utc_now(),
        )
    )
