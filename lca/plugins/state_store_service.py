"""State store Service Definition plugin — Tier-1."""
from __future__ import annotations

from typing import Any

from cordis import Context, plugin


@plugin(name="lca-state-store-service")
async def setup(ctx: Context, config: Any) -> None:
    from lca.layer0_infra.capability.state_store import StateStoreService
    ctx.provide("state_store", StateStoreService())
