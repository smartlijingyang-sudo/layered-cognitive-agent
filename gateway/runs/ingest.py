"""Attachment ingest: SSRF policy, cache, download, data URI."""

from __future__ import annotations

import base64
import ipaddress
import json
import re
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
import structlog
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from lca.contracts.models.core.sandbox import (
    SANDBOX_INIT_MAX_FILE_BYTES,
    SANDBOX_INIT_MAX_FILES,
)
from lca.layer0_infra.file_store import FileStore

MAX_INGEST_FILE_BYTES = SANDBOX_INIT_MAX_FILE_BYTES
MAX_INGEST_FILES = SANDBOX_INIT_MAX_FILES
FILE_DOWNLOAD_TIMEOUT_S = 120


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
    """Outcome of mirroring remote LobeHub files into LCA FileStore."""

    attachment_ids: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()


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


_ALLOWED_SCHEMES = frozenset({"http", "https"})


class IngestUrlPolicyError(Exception):
    """Raised when a remote URL is not permitted by ingest policy."""


def assert_ingest_url_allowed(
    url: str,
    settings: LobeHubBridgeSettings | None = None,
) -> None:
    """Validate ``url`` before outbound fetch (data URIs bypass this check)."""
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise IngestUrlPolicyError(f"unsupported URL scheme: {scheme or '(empty)'}")

    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise IngestUrlPolicyError("URL missing hostname")

    cfg = settings if settings is not None else bridge_settings()
    if host in cfg.allowed_hosts():
        return

    if cfg.ingest_allow_private_ip and _is_private_or_loopback(host):
        return

    raise IngestUrlPolicyError(f"host not allowed for ingest: {host}")


def _is_private_or_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(addr.is_private or addr.is_loopback or addr.is_link_local)


_CACHE_VERSION = 1


@dataclass(frozen=True)
class IngestCacheEntry:
    attachment_id: str
    lobehub_id: str
    url: str
    name: str
    size_bytes: int
    ingested_at: float


class IngestCache:
    """JSON-backed index: LobeHub file id or URL → LCA ``attachment_id``."""

    def __init__(
        self,
        path: Path,
        *,
        max_entries: int,
        store: FileStore,
    ) -> None:
        self._path = path
        self._max_entries = max_entries
        self._store = store
        self._lock = threading.Lock()
        self._entries: dict[str, IngestCacheEntry] = {}
        self._load()

    def resolve(self, ref: FileRef) -> str | None:
        """Return a valid cached ``attachment_id`` or ``None``."""
        key = _cache_key(ref)
        with self._lock:
            entry = self._entries.get(key)
        if entry is None:
            return None
        if not self._store.exists(entry.attachment_id):
            with self._lock:
                self._entries.pop(key, None)
                self._persist_unlocked()
            return None
        return entry.attachment_id

    def remember(self, ref: FileRef, attachment_id: str, *, size_bytes: int) -> None:
        key = _cache_key(ref)
        entry = IngestCacheEntry(
            attachment_id=attachment_id,
            lobehub_id=ref.lobehub_id,
            url=ref.url.strip(),
            name=ref.name,
            size_bytes=size_bytes,
            ingested_at=time.time(),
        )
        with self._lock:
            self._entries[key] = entry
            self._trim_unlocked()
            self._persist_unlocked()

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            raw: dict[str, Any] = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if raw.get("version") != _CACHE_VERSION:
            return
        items = raw.get("entries")
        if not isinstance(items, dict):
            return
        loaded: dict[str, IngestCacheEntry] = {}
        for key, value in items.items():
            if not isinstance(value, dict):
                continue
            try:
                loaded[str(key)] = IngestCacheEntry(
                    attachment_id=str(value["attachment_id"]),
                    lobehub_id=str(value.get("lobehub_id", "")),
                    url=str(value.get("url", "")),
                    name=str(value.get("name", "")),
                    size_bytes=int(value.get("size_bytes", 0)),
                    ingested_at=float(value.get("ingested_at", 0.0)),
                )
            except (KeyError, TypeError, ValueError):
                continue
        self._entries = loaded

    def _trim_unlocked(self) -> None:
        overflow = len(self._entries) - self._max_entries
        if overflow <= 0:
            return
        ranked = sorted(self._entries.items(), key=lambda item: item[1].ingested_at)
        for key, _ in ranked[:overflow]:
            self._entries.pop(key, None)

    def _persist_unlocked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": _CACHE_VERSION,
            "entries": {key: asdict(entry) for key, entry in self._entries.items()},
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)


def _cache_key(ref: FileRef) -> str:
    lobehub_id = ref.lobehub_id.strip()
    if lobehub_id:
        return f"id:{lobehub_id}"
    return f"url:{ref.url.strip()}"


_default_cache: IngestCache | None = None
_default_cache_key: tuple[str, int] | None = None
_default_cache_lock = threading.Lock()


def get_ingest_cache(
    store: FileStore, settings: LobeHubBridgeSettings | None = None
) -> IngestCache:
    global _default_cache, _default_cache_key
    cfg = settings if settings is not None else bridge_settings()
    cache_key = (cfg.ingest_cache_path, id(store))
    with _default_cache_lock:
        if _default_cache is None or _default_cache_key != cache_key:
            _default_cache = IngestCache(
                Path(cfg.ingest_cache_path),
                max_entries=cfg.ingest_cache_max_entries,
                store=store,
            )
            _default_cache_key = cache_key
        return _default_cache


def reset_ingest_cache_for_tests() -> None:
    global _default_cache, _default_cache_key
    with _default_cache_lock:
        _default_cache = None
        _default_cache_key = None


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
