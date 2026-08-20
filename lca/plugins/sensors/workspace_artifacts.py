"""Workspace-artifacts sensor plugin — Tier-2 named factory ``sensor.workspace-artifacts`` (PR3b)."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel

from lca.layer1_cognitive.sensors.workspace_artifacts import build_workspace_artifacts_sensor


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(name="sensor.workspace-artifacts")
async def setup(ctx: Context, config: Config) -> None:
    """Provide the named sensor factory ``sensor.workspace-artifacts``."""
    ctx.provide("sensor.workspace-artifacts", build_workspace_artifacts_sensor)
