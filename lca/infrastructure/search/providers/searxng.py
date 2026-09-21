"""SearXNG REST search provider — connects to local or self-hosted SearXNG."""

from __future__ import annotations

import time
from typing import Any

import httpx
import structlog

from lca.infrastructure.search.constants.constants import PROVIDER_SEARXNG
from lca.infrastructure.search.models.models import SearchHit, SearchResponse
from lca.infrastructure.search.settings.settings import SearchSettings, get_search_settings

_log = structlog.get_logger(__name__)


def searxng_available(settings: SearchSettings | None = None) -> bool:
    cfg = settings if settings is not None else get_search_settings()
    return bool(cfg.searxng_url and cfg.searxng_url.strip())


async def search_searxng(
    query: str,
    *,
    topic: str | None = None,
    time_range: str | None = None,
    settings: SearchSettings | None = None,
) -> SearchResponse:
    """Query SearXNG JSON endpoint."""
    cfg = settings if settings is not None else get_search_settings()
    base_url = cfg.searxng_url.rstrip("/")
    search_url = f"{base_url}/search"

    categories = "news" if topic == "news" else "general"
    params: dict[str, Any] = {
        "q": query,
        "format": "json",
        "categories": categories,
    }
    if time_range:
        params["time_range"] = time_range

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=cfg.request_timeout_s) as client:
            resp = await client.get(
                search_url,
                params=params,
                headers={"User-Agent": "Mozilla/5.0 (compatible; LCA-SearXNG/1.0)"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        _log.warning("searxng_search_failed", query=query, error=str(exc))
        return SearchResponse(
            query=query,
            provider=PROVIDER_SEARXNG,
            error=str(exc),
            latency_ms=latency_ms,
        )

    hits: list[SearchHit] = []
    raw_results = data.get("results") or []
    for item in raw_results[: cfg.searxng_max_results]:
        if not isinstance(item, dict):
            continue
        hits.append(
            SearchHit(
                title=str(item.get("title") or ""),
                url=str(item.get("url") or ""),
                content=str(item.get("content") or ""),
                score=float(item.get("score") or 0.0),
                published_date=str(item.get("publishedDate") or item.get("published_date") or ""),
            )
        )

    latency_ms = int((time.monotonic() - start) * 1000)
    return SearchResponse(
        query=query,
        provider=PROVIDER_SEARXNG,
        results=tuple(hits),
        latency_ms=latency_ms,
    )
