"""MustConsultAllMembers plugin — named factory ``gate.must-consult-all``."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.enums import DecisionGateName
from lca.contracts.protocols import DecisionGate
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    name="gate.must-consult-all",
    provides=["gate.must-consult-all"],
    requires=[],
    implements=[DecisionGate],
    layer="guard",
    side_effects="none",
    policy_class="control",
    description="DecisionGate that forces lead to consult every team member before responding.",
    test_suite="tests/test_refactor_guards.py::TestProgressiveDisclosureVocabulary::test_must_consult_all_rewrites_early_respond",
)
async def setup(ctx, config: Config) -> None:
    """Provide the named gate factory ``gate.must-consult-all``."""
    from lca.layer1_cognitive.brain.decision_gates.must_consult_all import MustConsultAllMembers

    ctx.provide("gate.must-consult-all", MustConsultAllMembers)
    # Register into the decision_gate component registry so require(...)
    # resolves through the named factory path too.
    try:
        registries = ctx.inject("registries")
    except Exception:
        registries = None
    if registries is not None:
        registries.components.register(
            "decision_gate", DecisionGateName.MUST_CONSULT_ALL, MustConsultAllMembers
        )
