"""MustConsultAllMembers contribution — posts onto GateService."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.enums import DecisionGateName
from lca.contracts.protocols import DecisionGate
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    name="gate.must-consult-all",
    requires=["gates"],
    implements=[DecisionGate],
    layer="guard",
    side_effects="none",
    policy_class="control",
    description="DecisionGate that forces lead to consult every team member before responding.",
    test_suite="tests/test_refactor_guards.py::TestProgressiveDisclosureVocabulary::test_must_consult_all_rewrites_early_respond",
)
async def setup(ctx, config: Config) -> None:
    from lca.layer1_cognitive.brain.decision_gates.must_consult_all import MustConsultAllMembers

    ctx.inject("gates").add(MustConsultAllMembers, id="must-consult-all", slot="consult", order=10)
    try:
        registries = ctx.inject("registries")
    except Exception:
        registries = None
    if registries is not None:
        registries.components.register(
            "decision_gate", DecisionGateName.MUST_CONSULT_ALL, MustConsultAllMembers
        )
