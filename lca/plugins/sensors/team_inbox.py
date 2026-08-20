"""Team-inbox sensor contribution — posts onto PerceiveService."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import Sensor
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    name="sensor.team-inbox",
    requires=["perceive"],
    implements=[Sensor],
    layer="sensor",
    side_effects="none",
    policy_class="observe",
    description="Perceive team inbox entries from the journal-backed RunStore.",
    test_suite="tests/test_sensors_v3.py",
)
async def setup(ctx, config: Config) -> None:
    from lca.layer1_cognitive.sensors.journal_backed import build_team_inbox_sensor

    ctx.inject("perceive").add(
        build_team_inbox_sensor,
        id="team-inbox",
        order=40,
        team_only=True,
        needs="store",
    )
