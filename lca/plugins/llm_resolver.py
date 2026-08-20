"""LLM Resolver plugin — Tier-2.

Policy of which `LLMAdapter` the gateway hands to agents on `/runs`.

Sole plugin that reads LLM_API_KEY. Profiles swap behavior by patching
`config.mode` / `config.api_key_env` / `config.base_url_env`. No module-level
singleton — the resolver is fetched from `ctx.inject("llm_resolver")` per
request, so two boot trees (production + `lca-ops debug tree`) never share
state.
"""

from __future__ import annotations

import os

from cordis import Context, plugin
from pydantic import BaseModel, Field

from lca.layer0_infra.llm_resolver import ProductionLLMResolver


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    mode: str = Field(default="auto", description="auto | real | mock | deepseek")
    api_key_env: str = Field(default="LLM_API_KEY")
    base_url_env: str = Field(default="LLM_BASE_URL")
    default_model: str = Field(default="deepseek-chat")
    # Optional direct overrides (env wins when these are None)
    api_key: str | None = None
    base_url: str | None = None


@plugin(name="lca-llm-resolver", inject=["llm"])
async def setup(ctx: Context, config: Config) -> None:
    """Build a resolver that picks an LLMAdapter from env or ctx.llm providers."""
    api_key = config.api_key or os.environ.get(config.api_key_env)
    base_url = config.base_url or os.environ.get(config.base_url_env)
    llm_svc = ctx.inject("llm")
    resolver = ProductionLLMResolver(
        mode=config.mode,
        api_key=api_key,
        base_url=base_url,
        default_model=config.default_model,
        llm_service=llm_svc,
    )
    ctx.provide("llm_resolver", resolver)
