"""Tools Service Definition plugin — Tier-1."""
from __future__ import annotations

from typing import Any

from cordis import Context, plugin


@plugin(name="lca-tools-service")
async def setup(ctx: Context, config: Any) -> None:
    from lca.layer0_infra.capability.tools import ToolsService
    ctx.provide("tools", ToolsService())
