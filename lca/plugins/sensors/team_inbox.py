"""Team-inbox sensor plugin — Tier-2 named factory ``sensor.team-inbox`` (PR9)."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel

from lca.layer1_cognitive.sensors.journal_backed import build_team_inbox_sensor


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(name="sensor.team-inbox")
async def setup(ctx: Context, config: Config) -> None:
    """Provide the named sensor factory ``sensor.team-inbox``."""
    ctx.provide("sensor.team-inbox", build_team_inbox_sensor)
