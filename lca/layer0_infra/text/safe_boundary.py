"""UTF-8 safe text boundary for sandbox streams and journal previews (ADR-0051)."""

from __future__ import annotations

_SURROGATE_START = 0xD800
_SURROGATE_END = 0xDFFF
_REPLACEMENT = "\ufffd"


def sanitize_stream_text(text: str) -> str:
    """Replace lone surrogate code points so UTF-8 encode never fails."""
    if not text:
        return text
    return "".join(
        _REPLACEMENT if _SURROGATE_START <= ord(ch) <= _SURROGATE_END else ch for ch in text
    )


def safe_utf8_encode(text: str) -> bytes:
    """Encode text to UTF-8 after surrogate sanitization."""
    return sanitize_stream_text(text).encode("utf-8")
