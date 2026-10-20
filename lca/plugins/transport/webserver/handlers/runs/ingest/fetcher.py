"""Remote byte-fetching adapters and content integrity validation for file ingest."""

from __future__ import annotations

import base64
import re
from typing import Protocol

import httpx

from lca.contracts.mechanisms.content.addressable import sha256_hex
from lca.plugins.transport.webserver.handlers.runs.ingest.models import (
    FILE_DOWNLOAD_TIMEOUT_S,
    FileIntegrityError,
    LobeHubBridgeSettings,
    bridge_settings,
)
from lca.plugins.transport.webserver.handlers.runs.ingest.policy import (
    assert_ingest_url_allowed,
)

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
_HTML_DOCTYPE = re.compile(rb"^\s*<!doctype\s+html", re.IGNORECASE)
_HTML_TAG = re.compile(rb"<html[\s>]", re.IGNORECASE)
_DATA_URI_RE = re.compile(r"^data:([^;,]+)?;base64,(.+)$", re.IGNORECASE | re.DOTALL)


def content_hash(content: bytes) -> str:
    """Return the SHA-256 digest used by the ingest cache integrity gate."""
    return sha256_hex(content)


def sniff_mime(content: bytes) -> str:
    """Detect a known file type from magic bytes, else ``application/octet-stream``.

    Never returns ``text/html``: an HTML error page must remain detectable as
    a non-file so ``validate_file_integrity`` can reject it.
    """
    for mime, magic in _MAGIC_BYTES.items():
        if len(content) >= len(magic) and content[: len(magic)] == magic:
            return mime
    return "application/octet-stream"


def resolve_actual_mime(content: bytes, declared: str, http_mime: str) -> str:
    """Derive the MIME used for validation and storage at the ingest boundary.

    A wire-declared MIME (``fileList``/``fileType``/data URI) is authoritative.
    LobeHub ``imageList`` items carry no MIME, so the content's magic bytes
    decide; only when neither the declared nor the content is known do we
    fall back to the HTTP Content-Type. ``text/html`` is never chosen here —
    a HTML fallback page served for an upload URL must stay detectable.
    """
    if declared and declared not in {"", "undefined", "plain/txt", "application/octet-stream"}:
        return declared
    detected = sniff_mime(content)
    if detected != "application/octet-stream":
        return detected
    if http_mime.lower().startswith("text/html"):
        return "application/octet-stream"
    return http_mime or "application/octet-stream"


def validate_file_integrity(
    content: bytes,
    declared_mime: str,
    actual_mime: str,
    name: str,
) -> None:
    """Reject HTML fallbacks, MIME mismatches, and invalid known magic bytes."""
    if looks_like_html(content) and not declared_mime.startswith("text/html"):
        raise FileIntegrityError(
            f"content is HTML but declared mime is {declared_mime!r} "
            f"(name={name!r}) — likely SPA fallback or error page"
        )
    if (
        actual_mime.startswith("text/html")
        and not declared_mime.startswith("text/html")
        and declared_mime not in {"", "application/octet-stream"}
    ):
        raise FileIntegrityError(
            f"HTTP content-type is {actual_mime!r} but declared mime is {declared_mime!r}"
        )
    expected_magic = _MAGIC_BYTES.get(declared_mime)
    if (
        expected_magic is not None
        and len(content) >= len(expected_magic)
        and not content[: len(expected_magic)].startswith(expected_magic)
    ):
        raise FileIntegrityError(f"magic bytes mismatch for {declared_mime!r} (name={name!r})")


def decode_data_uri(url: str) -> tuple[bytes, str]:
    """Decode a base64 data URI without bypassing later integrity validation."""
    match = _DATA_URI_RE.match(url.strip())
    if not match:
        raise ValueError("invalid data URI")
    mime = (match.group(1) or "application/octet-stream").strip()
    payload = match.group(2).strip()
    return base64.b64decode(payload, validate=False), mime


def looks_like_html(content: bytes) -> bool:
    """Detect an HTML document in the first response bytes."""
    head = content[:512]
    return bool(_HTML_DOCTYPE.search(head) or _HTML_TAG.search(head))


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


__all__ = [
    "FileFetcher",
    "HttpxFileFetcher",
    "content_hash",
    "decode_data_uri",
    "looks_like_html",
    "resolve_actual_mime",
    "sniff_mime",
    "validate_file_integrity",
]
