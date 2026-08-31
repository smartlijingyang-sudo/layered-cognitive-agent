"""Skill-catalog sensor contribution — posts onto PerceiveService."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols import Sensor
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="sensor.skill-catalog",
    requires=["perceive"],
    implements=[Sensor],
    layer="L1",
    effects="none",
    description="Perceive installed skill catalog entries.",
    test_suite="tests/test_sensors_v3.py",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G4_PERCEPTION,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G4_PERCEPTION,
        control_slot=ControlSlot.PERCEIVE_CONTEXT,
        scope=Scope.TURN,
        authority=("skills.catalog.read",),
        evidence=("perceive.skill-catalog.collected",),
        revision="v1",
    ),

    ownership=OwnershipDeclaration(
        reads=('plugin.serve',),
        emits=('plugin.served',),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.cognition.sensors.skill_catalog import build_skill_catalog_sensor

    ctx.require("perceive").add(
        build_skill_catalog_sensor, id="skill-catalog", order=60, needs="skills"
    )
