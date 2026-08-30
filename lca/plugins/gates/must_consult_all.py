"""MustConsultAllMembers contribution — posts onto GateService."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.enums import DecisionGateName
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols import DecisionGate
from lca.contracts.protocols.logic_address import LogicAddress
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


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
    functional_group=FunctionalGroup.G6_DECISION,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G6_DECISION,
        control_slot=ControlSlot.THINK_GUARD,
        scope=Scope.TURN,
        authority=("team.progress.read", "decision.rewrite"),
        evidence=("gate.must-consult-all.enforced",),
        revision="v1",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer1_cognitive.brain.decision_gates.must_consult_all import MustConsultAllMembers

    ctx.require("gates").add(
        MustConsultAllMembers,
        id=DecisionGateName.MUST_CONSULT_ALL.value,
        slot="consult",
        order=10,
    )
