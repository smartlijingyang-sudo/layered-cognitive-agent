"""Plan-derived action authority policy for declarative runtime plans.

The plan compiler owns projection orchestration. This module owns the focused
policy that derives the closed ActionType set an Agent may emit from resolved
plugin specifications and task-level restrictions.
"""

from __future__ import annotations

from collections.abc import Sequence

from lca.contracts.atoms.enums import ActionScope, ActionType
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    ActionAuthorityPlan,
    ActionScopeAuthority,
    PluginSpec,
)

_SCOPE_DEFAULT_ACTIONS: dict[ActionScope, frozenset[str]] = {
    ActionScope.SOLO: frozenset(
        {
            ActionType.RESPOND.value,
            ActionType.USE_TOOL.value,
            ActionType.STOP.value,
            ActionType.ASK_HUMAN.value,
        }
    ),
    ActionScope.MEMBER: frozenset(
        {
            ActionType.RESPOND.value,
            ActionType.USE_TOOL.value,
            ActionType.STOP.value,
            ActionType.ASK_HUMAN.value,
        }
    ),
    ActionScope.LEAD: frozenset(
        {
            ActionType.RESPOND.value,
            ActionType.USE_TOOL.value,
            ActionType.DELEGATE.value,
            ActionType.HANDOFF.value,
            ActionType.STOP.value,
            ActionType.ASK_HUMAN.value,
        }
    ),
}

_LEAD_GROUPS = frozenset({FunctionalGroup.G8_COLLAB, FunctionalGroup.G10_COMPOSITION})
_LEAD_GROUP_VALUES = frozenset(group.value.lower() for group in _LEAD_GROUPS)


def compile_action_authority(
    specs: Sequence[PluginSpec],
    *,
    task_contract: str = "",
) -> ActionAuthorityPlan:
    """Derive the closed action authority declared by a resolved plan.

    ``task_contract`` supports the existing ``!<action>`` carve-out syntax.
    Profile compilation remains responsible for supplying the resolved specs;
    this policy never resolves plugins or constructs runtime providers.
    """

    scope = _infer_action_scope(specs)
    forbidden = _task_contract_carve_out(task_contract)
    return ActionAuthorityPlan(
        allowed_actions=_SCOPE_DEFAULT_ACTIONS[scope],
        forbidden_actions=forbidden,
        scope=scope.value,
        scoped_actions=tuple(
            ActionScopeAuthority(
                scope=action_scope.value,
                allowed_actions=allowed_actions,
            )
            for action_scope, allowed_actions in _SCOPE_DEFAULT_ACTIONS.items()
        ),
    )


def _infer_action_scope(specs: Sequence[PluginSpec]) -> ActionScope:
    for spec in specs:
        group = str(spec.functional_group).lower()
        if group in _LEAD_GROUP_VALUES or "lead" in group:
            return ActionScope.LEAD
        if "member" in group or "team" in group:
            return ActionScope.MEMBER
    return ActionScope.SOLO


def _task_contract_carve_out(task_contract: str) -> frozenset[str]:
    if not task_contract.startswith("!"):
        return frozenset()
    action = task_contract[1:].strip()
    if not action:
        return frozenset()
    valid_actions = {item.value for item in ActionType}
    if action not in valid_actions:
        raise ValueError(f"unknown action carve-out: {action}")
    return frozenset({action})


__all__ = ["compile_action_authority"]
