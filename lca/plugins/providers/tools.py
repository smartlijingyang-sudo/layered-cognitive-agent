"""Tools Provider plugin — Tier-2 (tool factories)."""
from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    factories: list[str] = Field(default_factory=lambda: ["g2a"])


@plugin(name="lca-tools-provider", inject=["tools"])
async def setup(ctx: Context, config: Config) -> None:
    from lca.layer0_infra.tools.default_set import build_default_tools

    if "g2a" in config.factories:
        ctx.inject("tools").register_factory("g2a", build_default_tools)
