"""Absolutize LCA file product URLs for LobeHub frontend (cross-origin dev).

The public URL for file downloads is independent of the internal proxy URL.
``OPENAI_PROXY_URL`` is for LobeHub backend → LCA gateway communication
(often 127.0.0.1).  ``LCA_GATEWAY_PUBLIC_URL`` is for browser-facing
downloads (the actual IP/hostname).

This module is a thin re-export facade — the canonical implementation lives
in ``gateway.narrative.artifact_registry``.
"""

from __future__ import annotations

from gateway.narrative.artifact_registry import (
    absolutize_url as _absolutize_url,
)

_DEFAULT_GATEWAY_BASE = "http://127.0.0.1:8765"


def gateway_public_base() -> str:
    """Public HTTP base for ``GET /files/{id}`` (no trailing slash).

    Delegates to ``artifact_registry.gateway_public_base()``.
    """
    from gateway.narrative.artifact_registry import gateway_public_base as _base

    return _base()


def absolutize_file_part(part: dict, *, base: str | None = None) -> dict:
    """Return a copy with relative ``/files/…`` URLs made absolute."""
    from typing import Any

    out: dict[str, Any] = dict(part)
    url = out.get("url")
    if isinstance(url, str) and url.startswith("/"):
        out["url"] = _absolutize_url(url, base=base)
    return out


def absolutize_file_parts(
    parts: tuple[dict, ...] | list[dict],
    *,
    base: str | None = None,
) -> list[dict]:
    return [absolutize_file_part(p, base=base) for p in parts if isinstance(p, dict)]
