"""Contracts, limits, and settings for the LobeHub-to-FileStore ingest boundary."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from lca.contracts.models.core.sandbox import (
    SANDBOX_INIT_MAX_FILE_BYTES,
    SANDBOX_INIT_MAX_FILES,
)

MAX_INGEST_FILE_BYTES = SANDBOX_INIT_MAX_FILE_BYTES
MAX_INGEST_FILES = SANDBOX_INIT_MAX_FILES
FILE_DOWNLOAD_TIMEOUT_S = 120

_DEFAULT_ALLOWLIST = "localhost,127.0.0.1,lobe-minio,minio"
_DEFAULT_CACHE_PATH = "traces/lobehub_ingest_cache.json"


class FileIntegrityError(Exception):
    """Raised when downloaded content fails declared-file integrity validation."""


class IngestUrlPolicyError(Exception):
    """Raised when a remote URL is not permitted by the ingest policy."""


@dataclass(frozen=True)
class FileRef:
    """A user-uploaded asset referenced in OpenAI-style messages."""

    name: str
    url: str
    mime_type: str = "application/octet-stream"
    lobehub_id: str = ""
    size_bytes: int | None = None
    source: str = "file_tag"


@dataclass(frozen=True)
class IngestResult:
    """Outcome of mirroring remote LobeHub files into an LCA FileStore."""

    attachment_ids: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()


class LobeHubBridgeSettings(BaseSettings):
    """File-ingest policy for the LobeHub-to-LCA bridge."""

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
        """Return normalized names explicitly allowed for remote ingest."""
        parts = self.ingest_url_allowlist.replace(";", ",").split(",")
        return frozenset(host.strip().lower() for host in parts if host.strip())


def bridge_settings() -> LobeHubBridgeSettings:
    """Instantiate the bridge configuration from the configured environment."""
    return LobeHubBridgeSettings()


__all__ = [
    "FILE_DOWNLOAD_TIMEOUT_S",
    "MAX_INGEST_FILES",
    "MAX_INGEST_FILE_BYTES",
    "FileIntegrityError",
    "FileRef",
    "IngestResult",
    "IngestUrlPolicyError",
    "LobeHubBridgeSettings",
    "bridge_settings",
]
