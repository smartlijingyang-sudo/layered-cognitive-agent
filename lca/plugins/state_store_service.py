"""State store Service Definition plugin — Tier-1."""
from __future__ import annotations

from cordis import plugin


@plugin(name="lca-state-store-service")
async def setup(ctx, config) -> None:
    from lca.layer0_infra.capability.state_store import StateStoreService
    ctx.provide("state_store", StateStoreService())
