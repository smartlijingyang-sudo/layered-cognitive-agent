"""Member-status tracking — direct state update, not a hook.

The status update after a delegate action is core state management,
not an optional observation. It lives here as a direct function called
by DelegateOperation, not as a POST_ACT hook.

Retry logic lives here (not on the Board Protocol) to keep the Board
as a pure state container. Attempt counts are tracked on
``AgentState.delegate_attempts``, and the max-attempts limit is read
from ``AgentState.delegate_max_attempts`` (wired through the existing
TeamConfig → RunContext → AgentState pipe).
"""

from __future__ import annotations

from lca.contracts.decision import Decision, Observation
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
    """纯函数:不接触 AgentState/Board,只做分类决策,可穷举测试。"""
    if success:
        return RoleStatus.DONE
    if failure_kind == FAILURE_KIND_VALIDATION:
        return RoleStatus.FAILED
    if attempts_after >= max_attempts:
        return RoleStatus.FAILED
    return RoleStatus.PENDING


def update_member_status(state: AgentState, decision: Decision, observation: Observation) -> None:
    """Update the member status board after a delegate action completes."""
    board = state.member_status
    if board is None or decision.delegate_to is None:
        return
    role = decision.delegate_to.target_role
    if role is None or role not in board.required_roles:
        return

    if observation.success:
        state.member_status = board.mark(role, RoleStatus.DONE)
        return

    failure_kind = observation.extra.get(FAILURE_KIND, FAILURE_KIND_EXECUTION)
    attempts_after = state.delegate_attempts.get(role, 0) + 1
    state.delegate_attempts[role] = attempts_after

    new_status = _next_role_status(
        success=False,
        failure_kind=failure_kind,
        attempts_after=attempts_after,
        max_attempts=state.delegate_max_attempts,
    )
    state.member_status = board.mark(role, new_status)
