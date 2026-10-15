"""Shared HTTP utilities — CORS headers (SSOT)."""

from __future__ import annotations

# ── CORS ────────────────────────────────────────────────────

CORS_HEADERS: dict[str, str] = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PATCH, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": (
        "Content-Type, Authorization, Last-Event-ID, X-Lca-Token, x-lca-user-id"
    ),
    "Access-Control-Expose-Headers": "Content-Type, Content-Disposition",
}


def cors_headers(**extra: str) -> dict[str, str]:
    """Return CORS headers merged with caller-supplied extras."""
    if extra:
        return {**CORS_HEADERS, **extra}
    return dict(CORS_HEADERS)
