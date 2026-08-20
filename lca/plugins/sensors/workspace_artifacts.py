"""Workspace-artifacts sensor contribution — posts onto PerceiveService."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import Sensor
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    name="sensor.workspace-artifacts",
    requires=["perceive"],
    implements=[Sensor],
    layer="sensor",
    side_effects="none",
    policy_class="observe",
    description="Perceive workspace artifact file pointers for the AgentState snapshot.",
    test_suite="tests/test_sensors_v3.py",
)
async def setup(ctx, config: Config) -> None:
    from lca.layer1_cognitive.sensors.workspace_artifacts import (
        build_workspace_artifacts_sensor,
    )

    ctx.inject("perceive").add(build_workspace_artifacts_sensor, id="workspace-artifacts", order=20)
