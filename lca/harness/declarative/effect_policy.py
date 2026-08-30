"""Compile declared effect governance into an executable policy plan.

The compiler owns normalization of older PluginSpec entries that do not yet carry
an explicit governance declaration. New or changed effect semantics belong to the
PluginSpec declaration, not to the outer plan compiler or effect gateway.
"""

from __future__ import annotations

from lca.contracts.protocols.declarative_graph import EffectPolicyPlan
from lca.contracts.protocols.declarative_plugin import (
    EffectGovernanceDeclaration,
    PluginSpec,
)

_IMPLICIT_APPROVAL_EFFECTS: frozenset[str] = frozenset({"network", "filesystem", "world"})


def compile_effect_policy(specs: tuple[PluginSpec, ...]) -> EffectPolicyPlan:
    """Compile a plan-owned effect policy from active PluginSpec declarations.

    Explicit declarations take precedence. Existing PluginSpecs without an
    ``effect_governance`` entry retain the previous policy semantics during the
    incremental migration, so activation does not create a second runtime path.
    """
    effects = tuple(sorted({effect for spec in specs for effect in spec.effects})) or ("none",)
    declared = _declared_governance(specs)
    approval_required = tuple(
        effect for effect in effects if _governance_for(effect, declared).requires_approval
    )
    idempotency_required = tuple(
        effect for effect in effects if _governance_for(effect, declared).requires_idempotency
    )
    return EffectPolicyPlan(
        gateway_capability="effect.gateway",
        allowed_effects=effects,
        approval_required=approval_required,
        idempotency_required=idempotency_required,
    )


def _declared_governance(
    specs: tuple[PluginSpec, ...],
) -> dict[str, EffectGovernanceDeclaration]:
    """Merge equivalent declarations and reject contradictory effect governance."""
    declared: dict[str, EffectGovernanceDeclaration] = {}
    for spec in specs:
        for governance in spec.effect_governance:
            current = declared.get(governance.effect_class)
            if current is None:
                declared[governance.effect_class] = governance
                continue
            if current != governance:
                raise ValueError(
                    "PS-006: conflicting governance declarations for "
                    f"effect class {governance.effect_class!r}"
                )
    return declared


def _governance_for(
    effect: str,
    declared: dict[str, EffectGovernanceDeclaration],
) -> EffectGovernanceDeclaration:
    """Return explicit governance or the single migration default for an effect."""
    if effect in declared:
        return declared[effect]
    return EffectGovernanceDeclaration(
        effect_class=effect,
        requires_approval=effect in _IMPLICIT_APPROVAL_EFFECTS,
        requires_idempotency=effect != "none",
    )


__all__ = ["compile_effect_policy"]
