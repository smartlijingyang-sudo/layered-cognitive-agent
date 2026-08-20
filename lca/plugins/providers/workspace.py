"""Workspace Provider plugin — Tier-2 (placeholder).

Full WorkspaceService does not yet exist in lca/layer0_infra/workspace/.
This Tier-2 stub is a safe default that registers a no-op workspace.
"""
from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["local"])


@plugin(name="lca-workspace-provider", inject=["workspace"])
async def setup(ctx: Context, config: Config) -> None:
    """WorkspaceService does not exist yet; deferred to follow-up."""
    pass
