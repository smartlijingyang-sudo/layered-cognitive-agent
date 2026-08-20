"""Workspace-instructions sensor contribution — posts onto PerceiveService."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import Sensor
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    name="sensor.workspace-instructions",
    requires=["perceive"],
    implements=[Sensor],
    layer="sensor",
    side_effects="none",
    policy_class="observe",
    description="Perceive workspace instruction content for the AgentState snapshot.",
    test_suite="tests/test_sensors_v3.py",
)
async def setup(ctx, config: Config) -> None:
    from lca.layer1_cognitive.sensors.workspace_instructions import (
        build_workspace_instructions_sensor,
    )

    ctx.inject("perceive").add(
        build_workspace_instructions_sensor, id="workspace-instructions", order=50
    )
