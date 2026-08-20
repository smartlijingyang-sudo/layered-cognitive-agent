"""Clock sensor contribution — posts onto PerceiveService."""

from __future__ import annotations
from pydantic import BaseModel
from lca.contracts.protocols import Sensor
from lca.harness.plugin_api import plugin, PluginKind


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
)
async def setup(ctx, config: Config) -> None:
    from lca.layer1_cognitive.sensors.clock import build_clock_sensor

    ctx.inject("perceive").add(build_clock_sensor, id="clock", order=10)
