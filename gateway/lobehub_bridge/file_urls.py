"""Absolutize LCA file product URLs for LobeHub frontend (cross-origin dev)."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urljoin

_DEFAULT_GATEWAY_BASE = "http://127.0.0.1:8765"


def gateway_public_base() -> str:
    """Public HTTP base for ``GET /files/{id}`` (no trailing slash)."""
    raw = (
        os.environ.get("LCA_GATEWAY_PUBLIC_URL", "").strip()
        or os.environ.get("OPENAI_PROXY_URL", "").strip().removesuffix("/v1").rstrip("/")
        or _DEFAULT_GATEWAY_BASE
    )
    return raw.rstrip("/")


def absolutize_file_part(part: dict[str, Any], *, base: str | None = None) -> dict[str, Any]:
    """Return a copy with relative ``/files/…`` URLs made absolute."""
    out = dict(part)
    url = out.get("url")
    if isinstance(url, str) and url.startswith("/"):
        out["url"] = urljoin(f"{(base or gateway_public_base()).rstrip('/')}/", url.lstrip("/"))
    return out


def absolutize_file_parts(
    parts: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    *,
    base: str | None = None,
) -> list[dict[str, Any]]:
    return [absolutize_file_part(p, base=base) for p in parts if isinstance(p, dict)]
