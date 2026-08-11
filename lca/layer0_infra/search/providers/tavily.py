"""Tavily REST search provider — replaces tvly CLI for LCA gateway runs."""

from __future__ import annotations

import time
from typing import Any

import httpx
import structlog

from lca.layer0_infra.search.constants import NEWS_TOPIC_HINTS, PROVIDER_TAVILY
from lca.layer0_infra.search.models import SearchHit, SearchResponse
from lca.layer0_infra.search.settings import SearchSettings, get_search_settings

_log = structlog.get_logger(__name__)

_TAVILY_SEARCH_URL = "https://api.tavily.com/search"


def tavily_api_key_configured(settings: SearchSettings | None = None) -> bool:
    cfg = settings if settings is not None else get_search_settings()
    key = (cfg.tavily_api_key or "").strip()
    return bool(key)


def _is_news_query(query: str) -> bool:
    lowered = query.lower()
    return any(hint in lowered for hint in NEWS_TOPIC_HINTS)


async def search_tavily(
    query: str,
    *,
    topic: str | None = None,
    time_range: str | None = None,
    settings: SearchSettings | None = None,
) -> SearchResponse:
    cfg = settings if settings is not None else get_search_settings()
    api_key = (cfg.tavily_api_key or "").strip()
    if not api_key:
        return SearchResponse(
            query=query,
            provider=PROVIDER_TAVILY,
            error="TAVILY_API_KEY not configured",
        )

    body: dict[str, Any] = {
        "api_key": api_key,
        "query": query,
        "search_depth": cfg.tavily_search_depth,
        "max_results": cfg.tavily_max_results,
        "include_answer": True,
    }
    if topic:
        body["topic"] = topic
    elif _is_news_query(query):
        body["topic"] = "news"
    if time_range:
        body["time_range"] = time_range
    elif _is_news_query(query):
        body["time_range"] = "day"

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=cfg.request_timeout_s) as client:
            resp = await client.post(_TAVILY_SEARCH_URL, json=body)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        _log.warning("tavily_search_failed", query=query, error=str(exc))
        return SearchResponse(
            query=query,
            provider=PROVIDER_TAVILY,
            error=str(exc),
            latency_ms=int((time.monotonic() - start) * 1000),
        )

    hits: list[SearchHit] = []
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        hits.append(
            SearchHit(
                title=str(item.get("title") or ""),
                url=str(item.get("url") or ""),
                content=str(item.get("content") or ""),
                score=float(item.get("score") or 0.0),
                published_date=str(item.get("published_date") or ""),
            )
        )
    answer = str(data.get("answer") or "")
    latency_ms = int((time.monotonic() - start) * 1000)
    return SearchResponse(
        query=query,
        provider=PROVIDER_TAVILY,
        results=tuple(hits),
        answer=answer,
        latency_ms=latency_ms,
    )
