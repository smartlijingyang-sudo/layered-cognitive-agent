"""UTF-8 safe text boundary helpers and canonical truncation.

This package provides two pure-text utilities used across sandbox
streams, journal previews, and observation payloads:

- ``safe_boundary`` — surrogate sanitization for safe UTF-8 encoding.
- ``truncate`` — single canonical truncation with configurable suffix.
"""

from lca.infrastructure.text.safe_boundary import safe_utf8_encode, sanitize_stream_text
from lca.infrastructure.text.truncate import (
    ASCII_ELLIPSIS,
    ELLIPSIS,
    truncate_text,
)

__all__ = [
    "ASCII_ELLIPSIS",
    "ELLIPSIS",
    "safe_utf8_encode",
    "sanitize_stream_text",
    "truncate_text",
]
