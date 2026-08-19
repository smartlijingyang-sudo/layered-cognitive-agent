"""Memory Service Definition plugin — Tier-1."""
from __future__ import annotations

from cordis import plugin


@plugin(name="lca-memory-service")
async def setup(ctx, config) -> None:
    from lca.layer0_infra.capability.memory import MemoryService
    ctx.provide("memory", MemoryService())
