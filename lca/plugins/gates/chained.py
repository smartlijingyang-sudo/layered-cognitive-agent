from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from lca.cognition.brain.decision_gates.chained import ChainedDecisionGate
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols import DecisionGate
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.think.cognition import DecisionGateAssembler
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


class ChainedDecisionGateAssembler(DecisionGateAssembler):
    """Standard Gate strategy: apply profile-selected gates in slot order."""

    def assemble(self, *, gates: Sequence[DecisionGate]) -> DecisionGate:
        return ChainedDecisionGate(*gates)


@plugin(
    id="gates.chain.sequential",
    requires=["gates"],
    implements=[DecisionGateAssembler],
    layer="L1",
    effects="none",
    description="Select the standard sequential DecisionGate chain strategy.",
    test_suite="tests/test_cognitive_group_assembly.py",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G6_DECISION,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G6_DECISION,
        control_slot=ControlSlot.THINK_GUARD,
        scope=Scope.AGENT,
        authority=("gates.assemble",),
        evidence=("gates.chain.sequential.assembled",),
        revision="v1",
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    ctx.require("gates").set_assembler(ChainedDecisionGateAssembler(), id="sequential")


__all__ = ["ChainedDecisionGateAssembler"]
