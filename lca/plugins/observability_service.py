"""Observability Service Definition plugin — Tier-1."""
from __future__ import annotations

from cordis import plugin


@plugin(name="lca-observability-service")
async def setup(ctx, config) -> None:
    from lca.layer0_infra.capability.observability import ObservabilityService
    ctx.provide("observability", ObservabilityService())
