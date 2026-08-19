"""Transport Service Definition plugin — Tier-1."""
from __future__ import annotations

from cordis import plugin


@plugin(name="lca-transport-service")
async def setup(ctx, config) -> None:
    from lca.layer0_infra.capability.transport import TransportService
    ctx.provide("transport", TransportService())
