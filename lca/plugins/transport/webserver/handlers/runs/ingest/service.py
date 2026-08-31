"""Mirror selected LobeHub file references through the governed ingest pipeline."""

from __future__ import annotations

import re

import structlog

from lca.infrastructure.file_store import FileStore
from lca.plugins.transport.webserver.handlers.runs.ingest.cache import IngestCache, get_ingest_cache
from lca.plugins.transport.webserver.handlers.runs.ingest.fetcher import (
    FileFetcher,
    HttpxFileFetcher,
)
from lca.plugins.transport.webserver.handlers.runs.ingest.integrity import (
    content_hash,
    decode_data_uri,
    validate_file_integrity,
)
from lca.plugins.transport.webserver.handlers.runs.ingest.models import (
    MAX_INGEST_FILE_BYTES,
    MAX_INGEST_FILES,
    FileIntegrityError,
    FileRef,
    IngestResult,
    IngestUrlPolicyError,
    LobeHubBridgeSettings,
    bridge_settings,
)

_log = structlog.get_logger(__name__)
_LOCAL_FILE_URL_RE = re.compile(r"^/files/([a-z]+_[a-z0-9]+)$", re.IGNORECASE)


def select_ingest_files(refs: tuple[FileRef, ...]) -> tuple[FileRef, ...]:
    """Apply LobeHub-aligned size and count caps before any download is attempted."""
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
    """Mirror selected files through local, cache, and guarded remote paths."""
    cfg = settings if settings is not None else bridge_settings()
    active_fetcher = fetcher if fetcher is not None else HttpxFileFetcher(cfg)
    active_cache = cache if cache is not None else get_ingest_cache(store, cfg)
    attachment_ids: list[str] = []
    skipped: list[str] = []
    for ref in select_ingest_files(refs):
        local_id = try_resolve_local_file(ref, store)
        if local_id is not None:
            attachment_ids.append(local_id)
            _log.debug("file_resolved_locally", name=ref.name, attachment_id=local_id)
            continue
        cached_id = active_cache.resolve(ref)
        if cached_id is not None:
            attachment_ids.append(cached_id)
            continue
        try:
            data, mime = await load_bytes(ref, active_fetcher)
        except IngestUrlPolicyError as exc:
            _log.error(
                "lobehub_file_ingest_blocked",
                name=ref.name,
                url=ref.url,
                error=str(exc),
                hint="relative URLs must resolve to a local FileStore entry",
            )
            skipped.append(ref.name)
            continue
        except FileIntegrityError as exc:
            _log.warning(
                "lobehub_file_ingest_integrity",
                name=ref.name,
                url=ref.url,
                error=str(exc),
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
        stored = store.put(data=data, name=ref.name, mime_type=mime or ref.mime_type)
        active_cache.remember(
            ref,
            stored.attachment_id,
            size_bytes=len(data),
            content_hash=content_hash(data),
        )
        attachment_ids.append(stored.attachment_id)
    return IngestResult(attachment_ids=tuple(attachment_ids), skipped=tuple(skipped))


async def load_bytes(ref: FileRef, fetcher: FileFetcher) -> tuple[bytes, str]:
    """Load and integrity-check one data URI or policy-authorized remote file."""
    url = ref.url.strip()
    if url.startswith("data:"):
        data, mime = decode_data_uri(url)
        validate_file_integrity(data, ref.mime_type, mime, ref.name)
        return data, mime
    data, actual_mime = await fetcher.fetch(url)
    declared = ref.mime_type
    if declared and declared not in {"", "undefined", "plain/txt"}:
        validate_file_integrity(data, declared, actual_mime, ref.name)
        return data, declared
    validate_file_integrity(data, actual_mime, actual_mime, ref.name)
    return data, actual_mime


def try_resolve_local_file(ref: FileRef, store: FileStore | None) -> str | None:
    """Resolve local ``/files/{id}`` and LobeHub-ID references without HTTP."""
    # Defensive guard: callers that boot the gateway without a bootstrap_factory
    # (e.g. ``scripts/serve_observability.py``) historically arrived here with
    # ``store is None`` and surfaced ``AttributeError: 'NoneType' object has
    # no attribute 'exists'`` as a 500 on POST /runs for any message that
    # carried a ``fileList`` / ``imageList``. Returning ``None`` lets the
    # remote/cache/loader fallback path try to attach the file instead of
    # failing the whole run.
    if store is None:
        return None
    url = ref.url.strip()
    match = _LOCAL_FILE_URL_RE.match(url)
    if match is None:
        lobehub_id = ref.lobehub_id.strip()
        return lobehub_id if lobehub_id and store.exists(lobehub_id) else None
    attachment_id = match.group(1)
    return attachment_id if store.exists(attachment_id) else None


__all__ = ["ingest_file_refs", "load_bytes", "select_ingest_files", "try_resolve_local_file"]
