"""ArtifactRespondInjector contribution — posts onto GateService."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols import DecisionGate
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="gate.artifact-respond-injector",
    requires=["gates"],
    implements=[DecisionGate],
    layer="L1",
    effects="none",
    description="Inject artifact references into terminal respond actions.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G6_DECISION,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G6_DECISION,
        control_slot=ControlSlot.THINK_GUARD,
        scope=Scope.TURN,
        authority=("decision.read", "artifact.reference.inject"),
        evidence=("gate.artifact-respond-injector.applied",),
        revision="v1",
    ),

    ownership=OwnershipDeclaration(
        reads=('plugin.serve',),
        emits=('plugin.served',),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.cognition.brain.decision_gates.artifact_respond_injector import (
        ArtifactRespondInjector,
    )

    ctx.require("gates").add(
        ArtifactRespondInjector, id="artifact-respond-injector", slot="loop", order=50
    )
