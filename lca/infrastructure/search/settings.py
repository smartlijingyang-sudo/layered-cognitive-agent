"""Search plane configuration — Tavily API + LLM native fallback."""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from lca.infrastructure.search.constants import DEFAULT_SEARCH_PROVIDERS


class SearchSettings(BaseSettings):
    """Unified search settings (env prefix ``LCA_SEARCH_`` + shared ``TAVILY_API_KEY``).

    Examples::

        TAVILY_API_KEY=tvly-...
        LCA_SEARCH_PROVIDERS=tavily
        LCA_SEARCH_LLM_FALLBACK=true
        LLM_ENABLE_SEARCH=true
    """

    model_config = SettingsConfigDict(
        env_prefix="LCA_SEARCH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    providers: str = Field(
        default=",".join(DEFAULT_SEARCH_PROVIDERS),
        description="Comma-separated provider ids (tavily).",
    )
    tavily_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TAVILY_API_KEY", "LCA_SEARCH_TAVILY_API_KEY"),
        description="Tavily REST API key (shared with LobeHub server convention).",
    )
    tavily_max_results: int = Field(default=5, ge=1, le=20)
    tavily_search_depth: str = Field(default="basic")
    llm_fallback: bool = Field(
        default=True,
        description="When tool providers fail, enable Qwen enable_search on next LLM call.",
    )
    request_timeout_s: int = Field(default=30, ge=5, le=120)


@lru_cache
def get_search_settings() -> SearchSettings:
    return SearchSettings()


def configured_provider_ids() -> tuple[str, ...]:
    raw = get_search_settings().providers
    parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    return tuple(parts) if parts else DEFAULT_SEARCH_PROVIDERS
