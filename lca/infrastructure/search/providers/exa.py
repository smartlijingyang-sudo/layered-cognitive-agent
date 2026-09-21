"""Exa AI REST search provider — Neural Semantic Search and Highlights."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog

from lca.infrastructure.search.constants.constants import PROVIDER_EXA
from lca.infrastructure.search.models.models import SearchHit, SearchResponse
from lca.infrastructure.search.settings.settings import SearchSettings, get_search_settings

_log = structlog.get_logger(__name__)

_EXA_SEARCH_URL = "https://api.exa.ai/search"


def exa_api_key_configured(settings: SearchSettings | None = None) -> bool:
    cfg = settings if settings is not None else get_search_settings()
    key = (cfg.exa_api_key or os.environ.get("EXA_API_KEY") or "").strip()
    return bool(key)


async def search_exa(
    query: str,
    *,
    topic: str | None = None,
    time_range: str | None = None,
    settings: SearchSettings | None = None,
) -> SearchResponse:
    """Query Exa REST search endpoint with highlights and optional recency filter."""
    cfg = settings if settings is not None else get_search_settings()
    api_key = (cfg.exa_api_key or os.environ.get("EXA_API_KEY") or "").strip()
    if not api_key:
        return SearchResponse(
            query=query,
            provider=PROVIDER_EXA,
            error="EXA_API_KEY not configured",
        )

    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "query": query,
        "type": "auto",
        "numResults": cfg.exa_max_results,
        "contents": {"highlights": True},
    }
    if time_range:
        now = datetime.now(UTC)
        delta_map = {
            "day": timedelta(days=1),
            "week": timedelta(days=7),
            "month": timedelta(days=30),
            "year": timedelta(days=365),
        }
        delta = delta_map.get(str(time_range).strip().lower())
        if delta is not None:
            payload["startPublishedDate"] = (now - delta).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=cfg.request_timeout_s) as client:
            resp = await client.post(_EXA_SEARCH_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        _log.warning("exa_search_failed", query=query, error=str(exc))
        return SearchResponse(
            query=query,
            provider=PROVIDER_EXA,
            error=str(exc),
            latency_ms=latency_ms,
        )

    hits: list[SearchHit] = []
    raw_results = data.get("results") or []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        highlights = item.get("highlights") or []
        content = (
            "\n".join(str(h) for h in highlights)
            if isinstance(highlights, list)
            else str(highlights)
        )
        hits.append(
            SearchHit(
                title=str(item.get("title") or ""),
                url=str(item.get("url") or ""),
                content=content,
                score=float(item.get("score") or 0.0),
                published_date=str(item.get("publishedDate") or item.get("published_date") or ""),
            )
        )

    latency_ms = int((time.monotonic() - start) * 1000)
    return SearchResponse(
        query=query,
        provider=PROVIDER_EXA,
        results=tuple(hits),
        latency_ms=latency_ms,
    )


class ExaSearchProvider:
    """Exa Neural Search Provider Adapter."""

    @property
    def id(self) -> str:
        return PROVIDER_EXA

    def is_available(self, settings: SearchSettings | None = None) -> bool:
        import sys

        svc = sys.modules.get("lca.infrastructure.search.service.service")
        fn = (
            getattr(svc, "exa_api_key_configured", exa_api_key_configured)
            if svc
            else exa_api_key_configured
        )
        return fn(settings=settings)

    async def search(
        self,
        query: str,
        *,
        topic: str | None = None,
        time_range: str | None = None,
        settings: SearchSettings | None = None,
    ) -> SearchResponse:
        import sys

        svc = sys.modules.get("lca.infrastructure.search.service.service")
        fn = getattr(svc, "search_exa", search_exa) if svc else search_exa
        return await fn(query, topic=topic, time_range=time_range, settings=settings)
