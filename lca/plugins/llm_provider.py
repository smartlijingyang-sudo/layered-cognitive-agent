"""LLM Provider plugin — Tier-1 (placeholder; Tier-2 in lca/plugins/providers/)."""
from __future__ import annotations

from typing import Any

from cordis import Context, plugin


@plugin(name="lca-llm-provider", inject=["llm"])
async def setup(ctx: Context, config: Any) -> None:
    """Register default mock provider; real providers come from Tier-2 plugins."""
    from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
    ctx.inject("llm").register("mock", MockLLMAdapter())
