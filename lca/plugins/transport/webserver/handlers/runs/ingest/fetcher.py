"""Remote byte-fetching adapters for the file ingest boundary."""

from __future__ import annotations

from typing import Protocol

import httpx

from lca.plugins.transport.webserver.handlers.runs.ingest.models import (
    FILE_DOWNLOAD_TIMEOUT_S,
    LobeHubBridgeSettings,
    bridge_settings,
)
from lca.plugins.transport.webserver.handlers.runs.ingest.policy import assert_ingest_url_allowed


class FileFetcher(Protocol):
    """Retrieve content bytes and the actual transport MIME type for one URL."""

    async def fetch(self, url: str) -> tuple[bytes, str]: ...


class HttpxFileFetcher:
    """HTTP(S) downloader protected by the ingest URL policy and timeout."""

    def __init__(self, settings: LobeHubBridgeSettings | None = None) -> None:
        self._settings = settings if settings is not None else bridge_settings()

    async def fetch(self, url: str) -> tuple[bytes, str]:
        """Fetch one allowed URL and normalize its response MIME type."""
        assert_ingest_url_allowed(url, self._settings)
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(FILE_DOWNLOAD_TIMEOUT_S),
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "application/octet-stream")
            mime = content_type.split(";")[0].strip() or "application/octet-stream"
            return response.content, mime


__all__ = ["FileFetcher", "HttpxFileFetcher"]
