"""Workspace-instructions sensor plugin — Tier-2 named factory ``sensor.workspace-instructions`` (PR13)."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel

from lca.layer1_cognitive.sensors.workspace_instructions import build_workspace_instructions_sensor


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(name="sensor.workspace-instructions")
async def setup(ctx: Context, config: Config) -> None:
    """Provide the named sensor factory ``sensor.workspace-instructions``."""
    ctx.provide("sensor.workspace-instructions", build_workspace_instructions_sensor)
