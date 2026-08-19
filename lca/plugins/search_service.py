"""Search Service Definition plugin — Tier-1."""
from __future__ import annotations

from cordis import plugin


@plugin(name="lca-search-service")
async def setup(ctx, config) -> None:
    from lca.layer0_infra.capability.search import SearchService
    ctx.provide("search", SearchService())
