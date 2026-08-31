from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from lca.cognition.brain.decision_gates.chained import ChainedDecisionGate
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols import DecisionGate
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
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G6_DECISION, control_slots=(ControlSlot.THINK_GUARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.AGENT,)),
        authority=AuthorityContract(grants=("gates.assemble",)),
        observability=EvidenceContract(descriptors=("gates.chain.sequential.assembled",)),
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
