"""Sandbox Service Definition plugin — Tier-1."""
from __future__ import annotations

from cordis import plugin


@plugin(name="lca-sandbox-service")
async def setup(ctx, config) -> None:
    from lca.layer0_infra.capability.sandbox import SandboxService
    ctx.provide("sandbox", SandboxService())
