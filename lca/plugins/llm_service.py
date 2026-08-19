"""LLM Service Definition plugin — Tier-1."""
from __future__ import annotations

from cordis import plugin


@plugin(name="lca-llm-service")
async def setup(ctx, config) -> None:
    from lca.layer0_infra.capability.llm import LlmService
    ctx.provide("llm", LlmService())
