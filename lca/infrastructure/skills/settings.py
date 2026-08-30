"""Operational skill runtime settings (env prefix LCA_SKILL_)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_MARKET_BASE = "https://market.lobehub.com"
_DEFAULT_MARKET_CREDENTIALS = Path.home() / ".lobehub-market" / "credentials.json"


class SkillSettings(BaseSettings):
    """Gateway-side skill store configuration."""

    model_config = SettingsConfigDict(
        env_prefix="LCA_SKILL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    cache_dir: Path = Field(
        default_factory=lambda: Path.home() / ".lca" / "skills",
        description="Installed skill packages root",
    )
    market_base_url: str = Field(
        default=_DEFAULT_MARKET_BASE,
        description="LobeHub Market API base URL",
    )
    market_token: str | None = Field(
        default=None,
        description="Optional static Bearer for market search/list (overrides M2M)",
    )
    market_client_id: str | None = Field(
        default=None,
        description="M2M client id (or MARKET_CLIENT_ID / market-cli credentials file)",
    )
    market_client_secret: str | None = Field(
        default=None,
        description="M2M client secret (or MARKET_CLIENT_SECRET / credentials file)",
    )
    market_credentials_path: Path = Field(
        default=_DEFAULT_MARKET_CREDENTIALS,
        description="Path to @lobehub/market-cli credentials.json",
    )
    market_timeout_s: float = Field(default=60.0, ge=1.0)
    allowed_hosts: tuple[str, ...] = Field(
        default=(
            "market.lobehub.com",
            "lobehub.com",
            "raw.githubusercontent.com",
            "github.com",
            "www.github.com",
        ),
        description="Hosts permitted for import_from_url fetches",
    )


@lru_cache(maxsize=1)
def get_skill_settings() -> SkillSettings:
    return SkillSettings()
