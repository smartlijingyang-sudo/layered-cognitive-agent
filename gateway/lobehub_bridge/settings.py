"""LobeHub bridge configuration — pydantic-settings (env prefix ``LCA_LOBEHUB_``)."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_ALLOWLIST = "localhost,127.0.0.1,lobe-minio,minio"
_DEFAULT_CACHE_PATH = "traces/lobehub_ingest_cache.json"


class LobeHubBridgeSettings(BaseSettings):
    """File ingest policy for LobeHub → LCA bridge."""

    model_config = SettingsConfigDict(
        env_prefix="LCA_LOBEHUB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ingest_url_allowlist: str = Field(
        default=_DEFAULT_ALLOWLIST,
        description="Comma-separated hostnames permitted for HTTP(S) file ingest.",
    )
    ingest_allow_private_ip: bool = Field(
        default=True,
        description="Allow RFC1918/link-local targets (dev MinIO on LAN). Disable in production.",
    )
    ingest_cache_path: str = Field(
        default=_DEFAULT_CACHE_PATH,
        description="JSON index mapping LobeHub file id / URL → LCA attachment_id.",
    )
    ingest_cache_max_entries: int = Field(
        default=500,
        ge=1,
        description="LRU cap for ingest cache entries.",
    )

    def allowed_hosts(self) -> frozenset[str]:
        parts = self.ingest_url_allowlist.replace(";", ",").split(",")
        return frozenset(host.strip().lower() for host in parts if host.strip())


def bridge_settings() -> LobeHubBridgeSettings:
    return LobeHubBridgeSettings()
