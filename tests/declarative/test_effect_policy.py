"""Tests for plan-owned declarative effect governance."""

from __future__ import annotations

from dataclasses import replace

import pytest

from lca.contracts.protocols.declarative.declarative_common import (
    DeclarativeValidationError,
    SemanticPhase,
)
from lca.contracts.protocols.declarative.declarative_plugin import EffectGovernanceDeclaration
from lca.harness.declarative.compile.effect_policy import compile_effect_policy
from lca.plugins.phase_graph.common import standard_phase_spec


def _spec(
    plugin_id: str,
    *,
    effect: str,
    governance: tuple[EffectGovernanceDeclaration, ...] = (),
):
    return replace(
        standard_phase_spec(
            plugin_id=plugin_id,
            phase=SemanticPhase.PERCEIVE,
            module="tests.declarative.effect_policy",
            effects=(effect,),
        ),
        effect_governance=governance,
    )


def test_explicit_effect_governance_overrides_migration_default() -> None:
    spec = _spec(
        "effect.network.no-approval",
        effect="network",
        governance=(
            EffectGovernanceDeclaration(
                effect_class="network",
                requires_approval=False,
                requires_idempotency=False,
            ),
        ),
    )

    policy = compile_effect_policy((spec,))

    assert policy.allowed_effects == ("network",)
    assert policy.approval_required == ()
    assert policy.idempotency_required == ()


def test_undeclared_effect_governance_preserves_current_migration_policy() -> None:
    policy = compile_effect_policy((_spec("effect.tools", effect="tools"),))

    assert policy.allowed_effects == ("tools",)
    assert policy.approval_required == ()
    assert policy.idempotency_required == ("tools",)


def test_conflicting_effect_governance_is_rejected_at_compile_seam() -> None:
    approved = _spec(
        "effect.network.approved",
        effect="network",
        governance=(EffectGovernanceDeclaration("network", requires_approval=True),),
    )
    unapproved = _spec(
        "effect.network.unapproved",
        effect="network",
        governance=(EffectGovernanceDeclaration("network", requires_approval=False),),
    )

    with pytest.raises(ValueError, match="conflicting governance"):
        compile_effect_policy((approved, unapproved))


def test_effect_governance_must_reference_a_declared_effect() -> None:
    with pytest.raises(DeclarativeValidationError, match="must refer to an effect"):
        _spec(
            "effect.invalid",
            effect="none",
            governance=(EffectGovernanceDeclaration("tools"),),
        )
