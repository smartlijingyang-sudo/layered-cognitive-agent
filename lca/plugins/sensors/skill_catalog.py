"""Skill-catalog sensor contribution — posts onto PerceiveService."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import Sensor
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


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
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer1_cognitive.sensors.skill_catalog import build_skill_catalog_sensor

    ctx.inject("perceive").add(
        build_skill_catalog_sensor, id="skill-catalog", order=60, needs="skills"
    )
