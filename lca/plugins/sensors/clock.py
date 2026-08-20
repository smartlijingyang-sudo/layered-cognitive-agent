"""Clock sensor plugin — Tier-2 named factory ``sensor.clock`` (PR3b)."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import Sensor
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    name="sensor.clock",
    provides=["sensor.clock"],
    requires=[],
    implements=[Sensor],
    layer="sensor",
    side_effects="none",
    policy_class="observe",
    description="Perceive the wall clock for the AgentState snapshot.",
    test_suite="tests/test_sensors_v3.py",
)
async def setup(ctx, config: Config) -> None:
    """Provide the named sensor factory ``sensor.clock``."""
    from lca.layer1_cognitive.sensors.clock import build_clock_sensor

    ctx.provide("sensor.clock", build_clock_sensor)
