"""Unified search service — provider chain + LobeHub-aligned formatting."""

from __future__ import annotations

import html
from typing import Any

from lca.infrastructure.search.models.models import SearchHit, SearchResponse
from lca.infrastructure.search.providers import (
    get_search_provider,
)
from lca.infrastructure.search.scope.scope import mark_web_search_attempt
from lca.infrastructure.search.settings.settings import configured_provider_ids


def any_search_provider_available() -> bool:
    """Check whether at least one configured search provider is available."""
    for provider_id in configured_provider_ids():
        provider = get_search_provider(provider_id)
        if provider is not None and provider.is_available():
            return True
    return False


async def web_search(
    query: str,
    *,
    topic: str | None = None,
    time_range: str | None = None,
) -> SearchResponse:
    """Try configured providers in order; fallback gracefully on failures."""
    text = (query or "").strip()
    if not text:
        return SearchResponse(query="", provider="", error="empty query")

    last_error = "no search providers configured"
    for provider_id in configured_provider_ids():
        provider = get_search_provider(provider_id)
        if provider is None:
            last_error = f"unknown search provider: {provider_id}"
            continue

        if not provider.is_available():
            last_error = f"{provider_id} not configured or unavailable"
            continue

        result = await provider.search(text, topic=topic, time_range=time_range)
        mark_web_search_attempt(provider=provider_id, ok=result.ok, error=result.error)
        if result.ok:
            return result
        last_error = result.error or f"{provider_id} search failed"

    mark_web_search_attempt(provider="none", ok=False, error=last_error)
    return SearchResponse(query=text, provider="", error=last_error)


def format_search_content(response: SearchResponse) -> str:
    """Format results for tool observation + LobeHub web-browsing card content."""
    if not response.ok:
        return response.error or "search failed"

    parts: list[str] = []
    if response.answer:
        parts.append(f"**Summary:** {response.answer}")

    if response.results:
        parts.append("\n**Results:**")
        for idx, hit in enumerate(response.results, start=1):
            parts.append(_format_hit(idx, hit))

    return "\n".join(parts) if parts else "No results found."


def build_search_plugin_state(response: SearchResponse) -> dict[str, Any]:
    """LobeHub ``UniformSearchResponse``-shaped state for UI cards."""
    results = [
        {
            "title": hit.title,
            "url": hit.url,
            "content": hit.content,
            "score": hit.score,
            **({"publishedDate": hit.published_date} if hit.published_date else {}),
        }
        for hit in response.results
    ]
    state: dict[str, Any] = {
        "query": response.query,
        "resultNumbers": len(results),
        "results": results,
        "costTime": response.latency_ms,
        "success": response.ok,
    }
    if response.error:
        state["errorDetail"] = response.error
    return state


def _format_hit(index: int, hit: SearchHit) -> str:
    title = html.escape(hit.title or hit.url)
    url = html.escape(hit.url)
    line = f"{index}. [{title}]({url})"
    if hit.published_date:
        line += f" ({html.escape(hit.published_date)})"
    if hit.content:
        snippet = hit.content[:400].replace("\n", " ")
        line += f"\n   {html.escape(snippet)}"
    return line
