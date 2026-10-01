"""Compile declared effect governance into an executable policy plan.

The compiler owns normalization of older PluginSpec entries that do not yet carry
an explicit governance declaration. New or changed effect semantics belong to the
PluginSpec declaration, not to the outer plan compiler or effect gateway.
"""

from __future__ import annotations

from lca.contracts.protocols.declarative.declarative_1.declarative_graph import EffectPolicyPlan
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    EffectGovernanceDeclaration,
    PluginSpec,
)

_IMPLICIT_APPROVAL_EFFECTS: frozenset[str] = frozenset({"network", "filesystem", "world"})

# Policy vocabulary (compiler-owned, ADR-0221 migration-era).
#
# ``EffectGovernanceDeclaration.policy`` is free text at the contract level;
# the compiler interprets it with this vocabulary to project the plan-level
# approval / idempotency tuples:
#   "approval"            — the effect requires human approval
#   "idempotent"          — the effect requires idempotency
#   "approval+idempotent" — both
#   "none"                — neither
# Unrecognized tokens are ignored: the declaration author owns the
# semantics; the compiler only projects what it recognizes.
_POLICY_APPROVAL = "approval"
_POLICY_IDEMPOTENT = "idempotent"
_POLICY_NONE = "none"


def _policy_flags(policy: str) -> tuple[bool, bool]:
    """Project a policy string onto (requires_approval, requires_idempotency)."""
    tokens = {token.strip() for token in policy.split("+")}
    return (_POLICY_APPROVAL in tokens, _POLICY_IDEMPOTENT in tokens)


def _migration_policy(effect: str) -> str:
    """Encode the pre-ADR-0221 boolean semantics as a policy string."""
    tokens = []
    if effect in _IMPLICIT_APPROVAL_EFFECTS:
        tokens.append(_POLICY_APPROVAL)
    if effect != "none":
        tokens.append(_POLICY_IDEMPOTENT)
    return "+".join(tokens) if tokens else _POLICY_NONE


def compile_effect_policy(specs: tuple[PluginSpec, ...]) -> EffectPolicyPlan:
    """Compile a plan-owned effect policy from active PluginSpec declarations.

    Explicit declarations take precedence. Existing PluginSpecs without an
    ``effect_governance`` entry retain the previous policy semantics during the
    incremental migration, so activation does not create a second runtime path.
    """
    effects = tuple(sorted({effect for spec in specs for effect in spec.effects})) or ("none",)
    declared = _declared_governance(specs)
    approval_required = tuple(
        effect for effect in effects if _policy_flags(_governance_for(effect, declared).policy)[0]
    )
    idempotency_required = tuple(
        effect for effect in effects if _policy_flags(_governance_for(effect, declared).policy)[1]
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
        policy=_migration_policy(effect),
    )


__all__ = ["compile_effect_policy"]
