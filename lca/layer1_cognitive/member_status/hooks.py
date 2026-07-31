"""Member-status lifecycle hooks (post_act tracking only)."""

from __future__ import annotations

from typing import Any

from lca.contracts.enums import ActionType, RoleStatus
from lca.contracts.state import AgentState


async def track_member_status_hook(event_name: str, state: AgentState, **kwargs: Any) -> None:
    """post_act: after a successful/failed delegate, update member_status board."""
    del event_name
    decision = kwargs.get("decision")
    observation = kwargs.get("observation")
    board = state.member_status
    if decision is None or board is None:
        return
    if decision.action_type == ActionType.DELEGATE and decision.delegate_to is not None:
        role = decision.delegate_to.target_role
        if role and role in board.required_roles:
            new_status = (
                RoleStatus.DONE if getattr(observation, "success", False) else RoleStatus.FAILED
            )
            state.member_status = board.mark(role, new_status)


# Transitional alias — remove after one release cycle.
ledger_tracking_hook = track_member_status_hook
