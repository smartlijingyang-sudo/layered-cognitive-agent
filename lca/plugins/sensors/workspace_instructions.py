"""Workspace-instructions sensor contribution — posts onto PerceiveService."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols import Sensor
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="sensor.workspace-instructions",
    requires=["perceive"],
    implements=[Sensor],
    layer="L1",
    effects="none",
    description="Perceive workspace instruction content for the AgentState snapshot.",
    test_suite="tests/test_sensors_v3.py",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G4_PERCEPTION,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G4_PERCEPTION,
        control_slot=ControlSlot.PERCEIVE_CONTEXT,
        scope=Scope.TURN,
        authority=("workspace.instructions.read",),
        evidence=("perceive.workspace-instructions.collected",),
        revision="v1",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.cognition.sensors.workspace_instructions import (
        build_workspace_instructions_sensor,
    )

    ctx.require("perceive").add(
        build_workspace_instructions_sensor, id="workspace-instructions", order=50
    )
