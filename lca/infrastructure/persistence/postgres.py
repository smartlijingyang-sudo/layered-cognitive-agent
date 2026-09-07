"""Postgres connection helpers for LobeHub-adjacent durable stores (ADR-0200)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlparse


def database_url_from_env() -> str | None:
    """Return ``DATABASE_URL`` when set and looks like Postgres."""
    raw = os.environ.get("DATABASE_URL", "").strip()
    if not raw:
        return None
    scheme = urlparse(raw).scheme
    if scheme not in {"postgresql", "postgres"}:
        return None
    return raw


def postgres_available() -> bool:
    """True when ``DATABASE_URL`` points at Postgres and connects."""
    url = database_url_from_env()
    if url is None:
        return False
    try:
        with postgres_connection(url) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception:
        return False


@contextmanager
def postgres_connection(database_url: str | None = None) -> Iterator[Any]:
    """Open a sync ``psycopg`` connection (caller owns transaction semantics)."""
    url = (database_url or database_url_from_env() or "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured for Postgres")
    try:
        import psycopg  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "Postgres support requires psycopg. Install with: uv add psycopg[binary]"
        ) from exc
    parsed = urlparse(url)
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise ValueError(f"unsupported DATABASE_URL scheme: {parsed.scheme!r}")
    with psycopg.connect(url) as conn:
        yield conn


__all__ = ("database_url_from_env", "postgres_available", "postgres_connection")
