"""Clock sensor contribution — posts onto PerceiveService."""

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
    id="sensor.clock",
    requires=["perceive"],
    implements=[Sensor],
    layer="L1",
    effects="none",
    description="Perceive the wall clock for the AgentState snapshot.",
    test_suite="tests/test_sensors_v3.py",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G2_SPACETIME,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G2_SPACETIME,
        control_slot=ControlSlot.PERCEIVE_CONTEXT,
        scope=Scope.TURN,
        authority=("clock.read",),
        evidence=("perceive.clock.collected",),
        revision="v1",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.cognition.sensors.clock import build_clock_sensor

    ctx.require("perceive").add(build_clock_sensor, id="clock", order=10)
