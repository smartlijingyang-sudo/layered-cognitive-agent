"""Team-inbox sensor contribution — posts onto PerceiveService."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import Sensor
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
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer1_cognitive.sensors.journal_backed import build_team_inbox_sensor

    ctx.inject("perceive").add(
        build_team_inbox_sensor, id="team-inbox", order=40, team_only=True, needs="store"
    )
