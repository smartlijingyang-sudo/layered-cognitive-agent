"""Tools Service Definition plugin — Tier-1."""
from __future__ import annotations

from cordis import plugin


@plugin(name="lca-tools-service")
async def setup(ctx, config) -> None:
    from lca.layer0_infra.capability.tools import ToolsService
    ctx.provide("tools", ToolsService())
