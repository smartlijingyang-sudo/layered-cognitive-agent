"""Skill-catalog sensor plugin — Tier-2 named factory ``sensor.skill-catalog`` (PR14)."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import Sensor
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    name="sensor.skill-catalog",
    provides=["sensor.skill-catalog"],
    implements=[Sensor],
    layer="sensor",
    side_effects="none",
    policy_class="observe",
    description="Perceive installed skill catalog entries.",
    test_suite="tests/test_sensors_v3.py",
)
async def setup(ctx, config: Config) -> None:
    """Provide the named sensor factory ``sensor.skill-catalog``."""
    from lca.layer1_cognitive.sensors.skill_catalog import build_skill_catalog_sensor

    ctx.provide("sensor.skill-catalog", build_skill_catalog_sensor)
