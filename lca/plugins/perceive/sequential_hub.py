from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from lca.cognition.perceive_hub import SequentialPerceiveHub
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols import MemorySystem, PerceiveHub, Sensor
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.think.cognition import PerceiveHubAssembler
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


class SequentialPerceiveHubAssembler(PerceiveHubAssembler):
    """Standard PerceiveHub strategy: collect selected Sensors in order."""

    def assemble(
        self,
        *,
        sensors: Sequence[Sensor],
        memory: MemorySystem,
    ) -> PerceiveHub:
        return SequentialPerceiveHub(sensors=sensors, memory=memory)


@plugin(
    id="perceive.hub.sequential",
    requires=["perceive"],
    implements=[PerceiveHubAssembler],
    layer="L1",
    effects="none",
    description="Select the standard sequential PerceiveHub assembly strategy.",
    test_suite="tests/test_cognitive_group_assembly.py",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G4_PERCEPTION,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G4_PERCEPTION,
        control_slot=ControlSlot.PERCEIVE_CONTEXT,
        scope=Scope.AGENT,
        authority=("perceive.assemble",),
        evidence=("perceive.hub.sequential.assembled",),
        revision="v1",
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    ctx.require("perceive").set_assembler(SequentialPerceiveHubAssembler(), id="sequential")


__all__ = ["SequentialPerceiveHubAssembler"]
