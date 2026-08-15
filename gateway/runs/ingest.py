"""Attachment ingest: SSRF policy, integrity gates, cache, download, data URI.

Every file that enters the FileStore passes through integrity gates.
Pipeline: fetch → integrity check → store → cache.
If any gate rejects, the file is skipped — never stored as corrupt data.
"""

from __future__ import annotations

import base64
import hashlib
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

# ── Integrity Gates ──────────────────────────────────────────────────────

# Magic bytes for common file types.
# Used to detect content-type mismatches (e.g. HTML served instead of PDF).
_MAGIC_BYTES: dict[str, bytes] = {
    "application/pdf": b"%PDF",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": b"PK\x03\x04",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": b"PK\x03\x04",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": b"PK\x03\x04",
    "application/zip": b"PK\x03\x04",
    "image/png": b"\x89PNG",
    "image/jpeg": b"\xff\xd8\xff",
    "image/gif": b"GIF8",
}

# HTML detection thresholds.
_HTML_DOCTYPE = re.compile(rb"^\s*<!doctype\s+html", re.IGNORECASE)
_HTML_TAG = re.compile(rb"<html[\s>]", re.IGNORECASE)


class FileIntegrityError(Exception):
    """Raised when downloaded content fails integrity validation."""


def _looks_like_html(content: bytes) -> bool:
    """Heuristic: does the content look like an HTML document?"""
    head = content[:512]
    return bool(_HTML_DOCTYPE.search(head) or _HTML_TAG.search(head))


def validate_file_integrity(
    content: bytes,
    declared_mime: str,
    actual_mime: str,
    name: str,
) -> None:
    """Validate downloaded content matches declared type.

    Raises ``FileIntegrityError`` if content is corrupt or mismatched.
    Gates:
    1. If declared as non-HTML but content is HTML → reject (SPA fallback detection)
    2. If declared mime has known magic bytes, verify content starts with them
    3. If HTTP content-type is HTML but declared is not → reject
    """
    # Gate 1: HTML content detection.
    # If user uploaded a PDF/PPTX/Markdown but we got HTML, the server
    # likely returned a SPA fallback or error page.
    if _looks_like_html(content) and not declared_mime.startswith("text/html"):
        raise FileIntegrityError(
            f"content is HTML but declared mime is {declared_mime!r} "
            f"(name={name!r}) — likely SPA fallback or error page"
        )

    # Gate 2: HTTP content-type cross-check.
    # If the HTTP response says text/html but we declared application/pdf, reject.
    if (
        actual_mime.startswith("text/html")
        and not declared_mime.startswith("text/html")
        and declared_mime not in {"", "application/octet-stream"}
    ):
        raise FileIntegrityError(
            f"HTTP content-type is {actual_mime!r} but declared mime is {declared_mime!r}"
        )

    # Gate 3: Magic bytes verification.
    expected_magic = _MAGIC_BYTES.get(declared_mime)
    if (
        expected_magic is not None
        and len(content) >= len(expected_magic)
        and not content[: len(expected_magic)].startswith(expected_magic)
    ):
        raise FileIntegrityError(f"magic bytes mismatch for {declared_mime!r} (name={name!r})")


def content_hash(content: bytes) -> str:
    """SHA-256 hex digest for integrity verification."""
    return hashlib.sha256(content).hexdigest()


# ── FileRef / IngestResult ───────────────────────────────────────────────


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
    content_hash: str = ""
    """SHA-256 hex digest. Empty for legacy entries (pre-integrity)."""


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
        """Return a valid cached ``attachment_id`` or ``None``.

        Verifies content integrity: if the cache has a content_hash and the
        stored bytes don't match, the entry is invalidated.
        """
        key = _cache_key(ref)
        with self._lock:
            entry = self._entries.get(key)
        if entry is None:
            return None
        stored = self._store.get(entry.attachment_id)
        if stored is None:
            with self._lock:
                self._entries.pop(key, None)
                self._persist_unlocked()
            return None
        # Cache Gate: verify content hash if recorded.
        if entry.content_hash:
            raw = self._store.read_bytes(entry.attachment_id)
            if raw is not None and content_hash(raw) != entry.content_hash:
                _log.warning(
                    "ingest_cache_integrity_mismatch",
                    name=ref.name,
                    attachment_id=entry.attachment_id,
                )
                with self._lock:
                    self._entries.pop(key, None)
                    self._persist_unlocked()
                return None
        return entry.attachment_id

    def remember(
        self,
        ref: FileRef,
        attachment_id: str,
        *,
        size_bytes: int,
        content_hash: str = "",
    ) -> None:
        key = _cache_key(ref)
        entry = IngestCacheEntry(
            attachment_id=attachment_id,
            lobehub_id=ref.lobehub_id,
            url=ref.url.strip(),
            name=ref.name,
            size_bytes=size_bytes,
            ingested_at=time.time(),
            content_hash=content_hash,
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
                    content_hash=str(value.get("content_hash", "")),
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
    """Download referenced files and persist into LCA FileStore (best-effort).

    Each file passes through integrity gates before storage.
    Corrupt or mismatched content is rejected, never stored.
    """
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
        except FileIntegrityError as exc:
            _log.warning(
                "lobehub_file_ingest_integrity", name=ref.name, url=ref.url, error=str(exc)
            )
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
        active_cache.remember(
            ref,
            stored.attachment_id,
            size_bytes=len(data),
            content_hash=content_hash(data),
        )
        attachment_ids.append(stored.attachment_id)

    return IngestResult(attachment_ids=tuple(attachment_ids), skipped=tuple(skipped))


async def _load_bytes(
    ref: FileRef,
    fetcher: FileFetcher,
) -> tuple[bytes, str]:
    """Download file bytes with integrity validation.

    Returns (content, mime_type). The mime_type is the *actual* content-type
    from the HTTP response, not the declared type. Integrity gates ensure
    the content matches what was expected.

    Raises FileIntegrityError if content is corrupt.
    """
    url = ref.url.strip()
    if url.startswith("data:"):
        data, mime = _decode_data_uri(url)
        validate_file_integrity(data, ref.mime_type, mime, ref.name)
        return data, mime
    data, actual_mime = await fetcher.fetch(url)
    # Use declared mime if it's specific and not generic.
    # But always validate against actual content-type from HTTP.
    declared = ref.mime_type
    if declared and declared not in {"", "undefined", "plain/txt"}:
        validate_file_integrity(data, declared, actual_mime, ref.name)
        return data, declared
    validate_file_integrity(data, actual_mime, actual_mime, ref.name)
    return data, actual_mime


def _decode_data_uri(url: str) -> tuple[bytes, str]:
    match = _DATA_URI_RE.match(url.strip())
    if not match:
        raise ValueError("invalid data URI")
    mime = (match.group(1) or "application/octet-stream").strip()
    payload = match.group(2).strip()
    return base64.b64decode(payload, validate=False), mime
