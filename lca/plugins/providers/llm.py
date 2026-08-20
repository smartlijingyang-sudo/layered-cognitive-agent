"""LLM Provider plugin — Tier-2 canonical.

Single plugin per seam with a factory pattern: registers multiple provider
implementations and selects the active one via `config.mode`.

Profiles swap providers by patching:
  - `config.mode` (auto | real | deepseek | mock | pi_ai)
  - `config.providers` (list of allowed provider names)
  - `config.api_key` / `config.base_url` (real/deepseek creds)
"""
from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    mode: str = Field(default="auto", description="auto|real|deepseek|mock|pi_ai")
    providers: list[str] = Field(default_factory=lambda: ["mock", "real", "deepseek"])
    api_key: str | None = None
    base_url: str | None = None


@plugin(name="lca-llm-provider", inject=["llm"])
async def setup(ctx: Context, config: Config) -> None:
    from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
    from lca.layer0_infra.llm_adapter.openai_compat import OpenAICompatAdapter

    llm = ctx.inject("llm")
    target = config.mode
    if target == "auto":
        target = "real" if config.api_key else "mock"
    if target not in config.providers:
        target = config.providers[0]

    if "mock" in config.providers:
        llm.register("mock", MockLLMAdapter(), activate=(target == "mock"))
    if "real" in config.providers:
        llm.register("real", OpenAICompatAdapter(api_key=config.api_key, base_url=config.base_url), activate=(target == "real"))
    if "deepseek" in config.providers:
        # DeepSeek is OpenAI-compatible; reuse the adapter.
        base = config.base_url or "https://api.deepseek.com"
        llm.register(
            "deepseek",
            OpenAICompatAdapter(api_key=config.api_key, base_url=base),
            activate=(target == "deepseek"),
        )
    # "pi_ai" not yet implemented — registered as a stub provider below.
