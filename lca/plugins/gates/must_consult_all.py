"""MustConsultAllMembers contribution — posts onto GateService."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import DecisionGate
from lca.plugins._cordis_adapter import PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="gate.must-consult-all",
    requires=["gates"],
    implements=[DecisionGate],
    layer="L1",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description="DecisionGate that forces lead to consult every team member before responding.",
    test_suite="tests/test_refactor_guards.py::TestProgressiveDisclosureVocabulary::test_must_consult_all_rewrites_early_respond",
)
async def setup(ctx, config: Config) -> None:
    from lca.layer1_cognitive.brain.decision_gates.must_consult_all import MustConsultAllMembers

    ctx.inject("gates").add(MustConsultAllMembers, id="must-consult-all", slot="consult", order=10)
