"""Workspace-artifacts sensor plugin — Tier-2 named factory ``sensor.workspace-artifacts`` (PR3b)."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import Sensor
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    name="sensor.workspace-artifacts",
    provides=["sensor.workspace-artifacts"],
    implements=[Sensor],
    layer="sensor",
    side_effects="none",
    policy_class="observe",
    description="Perceive workspace artifact file pointers for the AgentState snapshot.",
    test_suite="tests/test_sensors_v3.py",
)
async def setup(ctx, config: Config) -> None:
    """Provide the named sensor factory ``sensor.workspace-artifacts``."""
    from lca.layer1_cognitive.sensors.workspace_artifacts import build_workspace_artifacts_sensor

    ctx.provide("sensor.workspace-artifacts", build_workspace_artifacts_sensor)
