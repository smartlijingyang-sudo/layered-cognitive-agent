"""Validate remote file bytes before they cross into the managed FileStore."""

from __future__ import annotations

import base64
import hashlib
import re

from lca.plugins.transport.webserver.handlers.runs.ingest.models import FileIntegrityError

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
    return hashlib.sha256(content).hexdigest()


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


__all__ = ["content_hash", "decode_data_uri", "looks_like_html", "validate_file_integrity"]
