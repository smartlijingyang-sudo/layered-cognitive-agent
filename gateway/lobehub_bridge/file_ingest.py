"""Mirror LobeHub-referenced files into LCA FileStore for sandbox mount."""

from __future__ import annotations

import base64
import re
from typing import Protocol

import httpx
import structlog

from gateway.lobehub_bridge.constants import (
    FILE_DOWNLOAD_TIMEOUT_S,
    MAX_INGEST_FILE_BYTES,
    MAX_INGEST_FILES,
)
from gateway.lobehub_bridge.ingest_cache import IngestCache, get_ingest_cache
from gateway.lobehub_bridge.models import FileRef, IngestResult
from gateway.lobehub_bridge.settings import LobeHubBridgeSettings, bridge_settings
from gateway.lobehub_bridge.url_policy import IngestUrlPolicyError, assert_ingest_url_allowed
from lca.layer0_infra.file_store import FileStore

_log = structlog.get_logger(__name__)

_DATA_URI_RE = re.compile(r"^data:([^;,]+)?;base64,(.+)$", re.IGNORECASE | re.DOTALL)


class FileFetcher(Protocol):
    async def fetch(self, url: str) -> tuple[bytes, str]: ...


class HttpxFileFetcher:
    """HTTP(S) downloader with SSRF policy and bounded timeout."""

    def __init__(self, settings: LobeHubBridgeSettings | None = None) -> None:
        self._settings = settings if settings is not None else bridge_settings()

    async def fetch(self, url: str) -> tuple[bytes, str]:
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


def select_ingest_files(refs: tuple[FileRef, ...]) -> tuple[FileRef, ...]:
    """Apply LobeHub-aligned size/count caps before download."""
    selected: list[FileRef] = []
    for ref in refs:
        if not ref.url.strip():
            continue
        if ref.size_bytes is not None and ref.size_bytes > MAX_INGEST_FILE_BYTES:
            continue
        selected.append(ref)
        if len(selected) >= MAX_INGEST_FILES:
            break
    return tuple(selected)


async def ingest_file_refs(
    refs: tuple[FileRef, ...],
    store: FileStore,
    *,
    fetcher: FileFetcher | None = None,
    cache: IngestCache | None = None,
    settings: LobeHubBridgeSettings | None = None,
) -> IngestResult:
    """Download referenced files and persist into LCA FileStore (best-effort)."""
    cfg = settings if settings is not None else bridge_settings()
    active_fetcher = fetcher if fetcher is not None else HttpxFileFetcher(cfg)
    active_cache = cache if cache is not None else get_ingest_cache(store, cfg)
    attachment_ids: list[str] = []
    skipped: list[str] = []

    for ref in select_ingest_files(refs):
        cached_id = active_cache.resolve(ref)
        if cached_id is not None:
            attachment_ids.append(cached_id)
            continue

        try:
            data, mime = await _load_bytes(ref, active_fetcher)
        except IngestUrlPolicyError as exc:
            _log.warning("lobehub_file_ingest_blocked", name=ref.name, url=ref.url, error=str(exc))
            skipped.append(ref.name)
            continue
        except Exception as exc:
            _log.warning("lobehub_file_ingest_failed", name=ref.name, url=ref.url, error=str(exc))
            skipped.append(ref.name)
            continue

        if len(data) > MAX_INGEST_FILE_BYTES:
            skipped.append(ref.name)
            continue

        stored = store.put(
            data=data,
            name=ref.name,
            mime_type=mime or ref.mime_type,
        )
        active_cache.remember(ref, stored.attachment_id, size_bytes=len(data))
        attachment_ids.append(stored.attachment_id)

    return IngestResult(attachment_ids=tuple(attachment_ids), skipped=tuple(skipped))


async def _load_bytes(
    ref: FileRef,
    fetcher: FileFetcher,
) -> tuple[bytes, str]:
    url = ref.url.strip()
    if url.startswith("data:"):
        return _decode_data_uri(url)
    data, mime = await fetcher.fetch(url)
    if ref.mime_type and ref.mime_type not in {"", "undefined", "plain/txt"}:
        return data, ref.mime_type
    return data, mime


def _decode_data_uri(url: str) -> tuple[bytes, str]:
    match = _DATA_URI_RE.match(url.strip())
    if not match:
        raise ValueError("invalid data URI")
    mime = (match.group(1) or "application/octet-stream").strip()
    payload = match.group(2).strip()
    return base64.b64decode(payload, validate=False), mime
