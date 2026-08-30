"""Workspace-artifacts sensor contribution — posts onto PerceiveService."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols import Sensor
from lca.contracts.protocols.logic_address import LogicAddress
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="sensor.workspace-artifacts",
    requires=["perceive"],
    implements=[Sensor],
    layer="L1",
    effects="none",
    description="Perceive workspace artifact file pointers for the AgentState snapshot.",
    test_suite="tests/test_sensors_v3.py",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G4_PERCEPTION,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G4_PERCEPTION,
        control_slot=ControlSlot.PERCEIVE_CONTEXT,
        scope=Scope.TURN,
        authority=("workspace.read",),
        evidence=("perceive.workspace-artifacts.collected",),
        revision="v1",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer1_cognitive.sensors.workspace_artifacts import build_workspace_artifacts_sensor

    ctx.require("perceive").add(
        build_workspace_artifacts_sensor, id="workspace-artifacts", order=20
    )
