"""Extract deduplicated ``FileRef`` values from OpenAI/LobeHub message payloads."""

from __future__ import annotations

import re
from typing import Any, cast
from urllib.parse import unquote, urlparse

from lca.plugins.transport.webserver.handlers.runs.ingest import FileRef

_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')
_FILE_TAG_RE = re.compile(
    r"<file\s+([^>]*?)(?:/>|>\s*.*?\s*</file>)",
    re.IGNORECASE | re.DOTALL,
)
_IMAGE_TAG_RE = re.compile(
    r"<image\s+([^>]*?)(?:/>|>\s*.*?\s*</image>)",
    re.IGNORECASE | re.DOTALL,
)
_DATA_URI_RE = re.compile(r"^data:([^;,]+)?;base64,", re.IGNORECASE)


def collect_file_refs(messages: list[Any]) -> list[FileRef]:
    """Extract unique file references from the current user-message payload."""
    seen_urls: set[str] = set()
    refs: list[FileRef] = []

    def add(ref: FileRef) -> None:
        url = ref.url.strip()
        if not url or url in seen_urls:
            return
        seen_urls.add(url)
        refs.append(ref)

    for item in messages:
        if not isinstance(item, dict):
            continue
        for ref in structured_file_refs(item):
            add(ref)
        for blob in content_blobs(item.get("content")):
            for match in _FILE_TAG_RE.finditer(blob):
                add(file_ref_from_attrs(match.group(1), source="file_tag"))
            for match in _IMAGE_TAG_RE.finditer(blob):
                add(
                    file_ref_from_attrs(
                        match.group(1),
                        source="image_tag",
                        default_mime="image/png",
                    )
                )
        content = item.get("content")
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict) or part.get("type") != "image_url":
                    continue
                image_url = part.get("image_url")
                url = ""
                if isinstance(image_url, dict):
                    url = str(image_url.get("url", "")).strip()
                elif isinstance(image_url, str):
                    url = image_url.strip()
                if not url:
                    continue
                add(
                    FileRef(
                        name=name_from_url(url),
                        url=url,
                        mime_type=mime_from_data_uri(url) or "image/png",
                        source="image_url",
                    )
                )
    return refs


def structured_file_refs(item: dict[str, Any]) -> list[FileRef]:
    """Read first-class file/image fields without scraping prompt markup."""
    refs: list[FileRef] = []
    raw_files = item.get("files")
    if raw_files is None:
        raw_files = item.get("fileList")
    if isinstance(raw_files, list):
        for part in raw_files:
            ref = file_ref_from_mapping(part, source="files")
            if ref is not None:
                refs.append(ref)
    raw_images = item.get("imageList")
    if isinstance(raw_images, list):
        for part in raw_images:
            if not isinstance(part, dict):
                continue
            url = str(part.get("url", "")).strip()
            if not url:
                continue
            name = str(part.get("alt") or part.get("name") or part.get("id") or "").strip()
            refs.append(
                FileRef(
                    name=name or name_from_url(url),
                    url=url,
                    mime_type=str(part.get("mime_type") or part.get("fileType") or "image/png"),
                    lobehub_id=str(part.get("id", "")),
                    source="imageList",
                )
            )
    return refs


def file_ref_from_mapping(part: Any, *, source: str) -> FileRef | None:
    """Translate one structured LobeHub file payload into a typed reference."""
    if not isinstance(part, dict):
        return None
    url = str(part.get("url", "")).strip()
    if not url or part.get("inaccessible"):
        return None
    name = str(part.get("name") or part.get("filename") or name_from_url(url)).strip()
    mime = str(
        part.get("mime_type")
        or part.get("fileType")
        or part.get("type")
        or "application/octet-stream"
    ).strip()
    size_raw = part.get("size")
    if size_raw is None:
        size_raw = part.get("size_bytes")
    size_ok = isinstance(size_raw, int) or (isinstance(size_raw, str) and size_raw.isdigit())
    size = int(cast("str", size_raw)) if size_ok else None
    return FileRef(
        name=name or "file",
        url=url,
        mime_type=mime or "application/octet-stream",
        lobehub_id=str(part.get("id", "")),
        size_bytes=size,
        source=source,
    )


def content_blobs(content: Any) -> list[str]:
    """Return text fields that may carry legacy file/image tags."""
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        return [
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
    return []


def file_ref_from_attrs(
    raw_attrs: str,
    *,
    source: str,
    default_mime: str = "application/octet-stream",
) -> FileRef:
    """Translate one legacy file/image tag attribute string into a typed reference."""
    attrs = parse_attrs(raw_attrs)
    name = (
        attrs.get("name") or attrs.get("filename") or name_from_url(attrs.get("url", ""))
    ).strip()
    url = attrs.get("url", "").strip()
    mime = (attrs.get("type") or attrs.get("fileType") or default_mime).strip() or default_mime
    size_raw = attrs.get("size", "").strip()
    size = int(size_raw) if size_raw.isdigit() else None
    if attrs.get("error"):
        return FileRef(
            name=name or "file",
            url="",
            mime_type=mime,
            lobehub_id=attrs.get("id", ""),
            source=source,
        )
    return FileRef(
        name=name or "file",
        url=url,
        mime_type=mime,
        lobehub_id=attrs.get("id", ""),
        size_bytes=size,
        source=source,
    )


def parse_attrs(raw: str) -> dict[str, str]:
    """Decode a legacy XML-style attribute fragment."""
    return {key: unquote(value) for key, value in _ATTR_RE.findall(raw)}


def name_from_url(url: str) -> str:
    """Derive a stable display name for URL and data-URI file references."""
    if url.startswith("data:"):
        mime = mime_from_data_uri(url) or "application/octet-stream"
        ext = mime.split("/")[-1] if "/" in mime else "bin"
        return f"upload.{ext}"
    path = urlparse(url).path
    base = path.rsplit("/", 1)[-1] if path else "file"
    return unquote(base) or "file"


def mime_from_data_uri(url: str) -> str | None:
    """Return the declared MIME type from a data URI, if one is present."""
    match = _DATA_URI_RE.match(url)
    if not match:
        return None
    return (match.group(1) or "application/octet-stream").strip()


__all__ = [
    "collect_file_refs",
    "content_blobs",
    "file_ref_from_attrs",
    "file_ref_from_mapping",
    "mime_from_data_uri",
    "name_from_url",
    "parse_attrs",
    "structured_file_refs",
]
