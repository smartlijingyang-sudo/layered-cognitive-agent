"""Absolutize LCA file product URLs for LobeHub frontend (cross-origin dev).

The public URL for file downloads is independent of the internal proxy URL.
``OPENAI_PROXY_URL`` is for LobeHub backend → LCA gateway communication
(often 127.0.0.1).  ``LCA_GATEWAY_PUBLIC_URL`` is for browser-facing
downloads (the actual IP/hostname).
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urljoin

_DEFAULT_GATEWAY_BASE = "http://127.0.0.1:8765"


def gateway_public_base() -> str:
    """Public HTTP base for ``GET /files/{id}`` (no trailing slash).

    Priority:
        1. LCA_GATEWAY_PUBLIC_URL (explicit override)
        2. OPENAI_PROXY_URL (derived from proxy config)
        3. Default localhost fallback
    """
    raw = (
        os.environ.get("LCA_GATEWAY_PUBLIC_URL", "").strip()
        or os.environ.get("OPENAI_PROXY_URL", "").strip().removesuffix("/v1").rstrip("/")
        or _DEFAULT_GATEWAY_BASE
    )
    return raw.rstrip("/")


def absolutize_url(url: str, *, base: str | None = None) -> str:
    """Convert a relative URL to absolute using the public gateway base."""
    if not url:
        return url
    if url.startswith(("http://", "https://")):
        return url  # Already absolute
    if url.startswith("/"):
        base_url = (base or gateway_public_base()).rstrip("/")
        return urljoin(f"{base_url}/", url.lstrip("/"))
    return url


def absolutize_file_part(part: dict, *, base: str | None = None) -> dict:
    """Return a copy with relative ``/files/…`` URLs made absolute."""
    out: dict[str, Any] = dict(part)
    url = out.get("url")
    if isinstance(url, str) and url.startswith("/"):
        out["url"] = absolutize_url(url, base=base)
    return out


def absolutize_file_parts(
    parts: tuple[dict, ...] | list[dict],
    *,
    base: str | None = None,
) -> list[dict]:
    return [absolutize_file_part(p, base=base) for p in parts if isinstance(p, dict)]
