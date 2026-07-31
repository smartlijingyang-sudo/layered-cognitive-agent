"""Member-status tracking — direct state update, not a hook.

The status update after a delegate action is core state management,
not an optional observation. It lives here as a direct function called
by DelegateOperation, not as a POST_ACT hook.
"""

from __future__ import annotations

from lca.contracts.decision import Decision, Observation
from lca.contracts.enums import RoleStatus
from lca.contracts.state import AgentState


def update_member_status(state: AgentState, decision: Decision, observation: Observation) -> None:
    """Update the member status board after a delegate action completes."""
    board = state.member_status
    if board is None or decision.delegate_to is None:
        return
    role = decision.delegate_to.target_role
    if role and role in board.required_roles:
        new_status = RoleStatus.DONE if observation.success else RoleStatus.FAILED
        state.member_status = board.mark(role, new_status)
