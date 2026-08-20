"""Workspace-instructions sensor plugin — Tier-2 named factory ``sensor.workspace-instructions`` (PR13)."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import Sensor
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    name="sensor.workspace-instructions",
    provides=["sensor.workspace-instructions"],
    implements=[Sensor],
    layer="sensor",
    side_effects="none",
    policy_class="observe",
    description="Perceive workspace instruction content for the AgentState snapshot.",
    test_suite="tests/test_sensors_v3.py",
)
async def setup(ctx, config: Config) -> None:
    """Provide the named sensor factory ``sensor.workspace-instructions``."""
    from lca.layer1_cognitive.sensors.workspace_instructions import (
        build_workspace_instructions_sensor,
    )

    ctx.provide("sensor.workspace-instructions", build_workspace_instructions_sensor)
