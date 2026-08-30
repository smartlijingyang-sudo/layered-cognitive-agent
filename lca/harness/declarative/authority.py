"""Authority decisions derived from immutable declarative plan values."""

from __future__ import annotations

from lca.contracts.atoms.enums import ActionScope
from lca.contracts.protocols.declarative_phase_graph import ActionAuthorityPlan


def action_authority_for_scope(
    authority: ActionAuthorityPlan, scope: ActionScope
) -> ActionAuthorityPlan:
    """Select the already-compiled action grant for one Agent role scope.

    Team composition can close members and a lead from one immutable run plan.
    The selection therefore happens at the composition seam, but it never
    derives actions or introduces a fallback: an undeclared scope is a
    plan-closure error.
    """

    scope_name = scope.value
    for scoped_authority in authority.scoped_actions:
        if scoped_authority.scope == scope_name:
            return ActionAuthorityPlan(
                allowed_actions=scoped_authority.allowed_actions,
                forbidden_actions=authority.forbidden_actions,
                scope=scope_name,
            )
    raise ValueError(f"compiled action authority does not declare scope: {scope_name}")


def action_is_permitted(authority: ActionAuthorityPlan, action_type: str) -> bool:
    """Return whether ``action_type`` is permitted by a compiled authority plan.

    The authority plan declares the closed allowed and denied sets.  Evaluating
    those sets belongs to the Harness policy layer, not to the contract value.
    """

    if not isinstance(action_type, str) or not action_type:
        raise ValueError("action_type must be a non-empty string")
    return (
        action_type not in authority.forbidden_actions and action_type in authority.allowed_actions
    )


__all__ = ["action_authority_for_scope", "action_is_permitted"]
