"""Skill-catalog sensor plugin — Tier-2 named factory ``sensor.skill-catalog`` (PR14)."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel

from lca.layer1_cognitive.sensors.skill_catalog import build_skill_catalog_sensor


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(name="sensor.skill-catalog")
async def setup(ctx: Context, config: Config) -> None:
    """Provide the named sensor factory ``sensor.skill-catalog``."""
    ctx.provide("sensor.skill-catalog", build_skill_catalog_sensor)
