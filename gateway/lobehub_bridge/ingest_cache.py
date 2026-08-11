"""Persistent LobeHub file → LCA attachment_id index (cross-turn dedupe)."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from gateway.lobehub_bridge.models import FileRef
from gateway.lobehub_bridge.settings import LobeHubBridgeSettings, bridge_settings
from lca.layer0_infra.file_store import FileStore

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
