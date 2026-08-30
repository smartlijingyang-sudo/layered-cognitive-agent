"""Local file product store — shared by gateway upload and write_file tool.

Layout (under root, default ``traces/files``)::

    {attachment_id}/meta.json
    {attachment_id}/blob   # raw bytes (original name in meta)

Mirrors the LobeHub pattern of id → metadata + blob without S3 for MVP.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from lca.contracts.atoms.ids import new_id

_DEFAULT_ROOT = Path("traces/files")
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_NAME_LEN = 180


@dataclass(frozen=True)
class StoredFile:
    """A2A-aligned file product metadata."""

    attachment_id: str
    name: str
    mime_type: str
    size_bytes: int
    url: str
    conversation_id: str | None = None
    previewable: bool = False


class FileStore(Protocol):
    def put(
        self,
        *,
        data: bytes,
        name: str,
        mime_type: str,
        conversation_id: str | None = None,
    ) -> StoredFile: ...

    def get(self, attachment_id: str) -> StoredFile | None: ...

    def read_bytes(self, attachment_id: str) -> bytes | None: ...

    def exists(self, attachment_id: str) -> bool: ...


def _safe_filename(name: str) -> str:
    base = Path(name).name.strip() or "file"
    cleaned = _SAFE_NAME_RE.sub("_", base).strip("._") or "file"
    return cleaned[:_MAX_NAME_LEN]


def file_part_from_stored(stored: StoredFile) -> dict[str, object]:
    """Canonical product part — one shape for plugin_state.files and ToolInvoked.files."""
    return {
        "name": stored.name,
        "mimeType": stored.mime_type,
        "sizeBytes": stored.size_bytes,
        "url": stored.url,
        "previewable": stored.previewable,
        "attachmentId": stored.attachment_id,
    }


def persist_generated_files(store: FileStore, files: Sequence[object]) -> list[dict[str, object]]:
    """Store harvested sandbox bytes once; return canonical file parts."""
    parts: list[dict[str, object]] = []
    for item in files:
        data = getattr(item, "data", None)
        name = getattr(item, "name", "")
        mime = getattr(item, "mime_type", "") or "application/octet-stream"
        if not isinstance(data, (bytes, bytearray)) or not name:
            continue
        parts.append(
            file_part_from_stored(store.put(data=bytes(data), name=str(name), mime_type=str(mime)))
        )
    return parts


def _is_previewable(mime_type: str, name: str) -> bool:
    """UI may open an in-app preview (iframe / markdown / image), not download-only.

    Aligns with LobeHub FilePreview coverage for common agent products.
    """
    mime = mime_type.lower().split(";")[0].strip()
    lower = name.lower()
    if mime.startswith("image/"):
        return True
    if mime.startswith("text/"):
        return True
    if mime in {
        "application/json",
        "application/javascript",
        "application/xml",
        "application/xhtml+xml",
        "application/pdf",
    }:
        return True
    return lower.endswith(
        (
            ".html",
            ".htm",
            ".md",
            ".markdown",
            ".txt",
            ".csv",
            ".json",
            ".xml",
            ".svg",
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".webp",
        )
    )


class LocalFileStore:
    """Filesystem-backed FileStore with JSON sidecars."""

    def __init__(self, root: Path | None = None, *, public_url_prefix: str = "/files") -> None:
        self._root = (root if root is not None else _DEFAULT_ROOT).resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._url_prefix = public_url_prefix.rstrip("/")

    @property
    def root(self) -> Path:
        return self._root

    def put(
        self,
        *,
        data: bytes,
        name: str,
        mime_type: str,
        conversation_id: str | None = None,
    ) -> StoredFile:
        attachment_id = new_id("file")
        directory = self._root / attachment_id
        directory.mkdir(parents=True, exist_ok=False)
        safe_name = _safe_filename(name)
        blob_path = directory / "blob"
        blob_path.write_bytes(data)
        mime = (mime_type or "application/octet-stream").strip() or "application/octet-stream"
        stored = StoredFile(
            attachment_id=attachment_id,
            name=safe_name if safe_name != "file" or not name else Path(name).name,
            mime_type=mime,
            size_bytes=len(data),
            url=f"{self._url_prefix}/{attachment_id}",
            conversation_id=conversation_id,
            previewable=_is_previewable(mime, name),
        )
        # Prefer original display name (sanitized path segment already on disk name)
        display_name = Path(name).name.strip() or stored.name
        stored = StoredFile(
            attachment_id=stored.attachment_id,
            name=display_name,
            mime_type=stored.mime_type,
            size_bytes=stored.size_bytes,
            url=stored.url,
            conversation_id=conversation_id,
            previewable=stored.previewable,
        )
        (directory / "meta.json").write_text(
            json.dumps(asdict(stored), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return stored

    def get(self, attachment_id: str) -> StoredFile | None:
        meta_path = self._root / attachment_id / "meta.json"
        if not meta_path.is_file():
            return None
        try:
            raw = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        try:
            return StoredFile(
                attachment_id=str(raw["attachment_id"]),
                name=str(raw["name"]),
                mime_type=str(raw["mime_type"]),
                size_bytes=int(raw["size_bytes"]),
                url=str(raw.get("url") or f"{self._url_prefix}/{attachment_id}"),
                conversation_id=raw.get("conversation_id"),
                previewable=bool(raw.get("previewable", False)),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def read_bytes(self, attachment_id: str) -> bytes | None:
        blob = self._root / attachment_id / "blob"
        if not blob.is_file():
            return None
        return blob.read_bytes()

    def exists(self, attachment_id: str) -> bool:
        return (self._root / attachment_id / "meta.json").is_file()

    def read_text_preview(self, attachment_id: str, *, max_chars: int = 4000) -> str | None:
        data = self.read_bytes(attachment_id)
        if data is None:
            return None
        meta = self.get(attachment_id)
        if meta is None:
            return None
        mime = meta.mime_type.lower().split(";", 1)[0].strip()
        # Hint only — never dump HTML/XML the agent will read via tools.
        if mime in {"text/html", "text/xml", "application/xml", "application/xhtml+xml"}:
            return None
        if not (
            mime.startswith("text/")
            or mime in {"application/json", "application/javascript"}
            or meta.name.lower().endswith((".md", ".txt", ".csv", ".json", ".py", ".ts"))
        ):
            return None
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return None
        if len(text) > max_chars:
            return text[:max_chars] + "…"
        return text



