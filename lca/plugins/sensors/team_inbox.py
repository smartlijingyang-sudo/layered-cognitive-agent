"""Team-inbox sensor contribution — posts onto PerceiveService."""

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
    id="sensor.team-inbox",
    requires=["perceive"],
    implements=[Sensor],
    layer="L1",
    effects="none",
    description="Perceive team inbox entries from the journal-backed RunStore.",
    test_suite="tests/test_sensors_v3.py",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G4_PERCEPTION,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G4_PERCEPTION,
        control_slot=ControlSlot.PERCEIVE_CONTEXT,
        scope=Scope.TURN,
        authority=("team.inbox.read",),
        evidence=("perceive.team-inbox.collected",),
        revision="v1",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer1_cognitive.sensors.journal_backed import build_team_inbox_sensor

    ctx.require("perceive").add(
        build_team_inbox_sensor, id="team-inbox", order=40, team_only=True, needs="store"
    )
