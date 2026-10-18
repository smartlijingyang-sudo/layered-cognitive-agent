"""Pin the WebSearchExecutor dual-dispatch decision (RA-148).

The executor declares two backends: the kernel SearchService (Definition
seam) when provided, and the infrastructure ambient web_search when
search=None. The executed seam must be visible through the interface
(Observation.extra["search_seam"]) so the routing decision is testable
through the interface instead of hidden behind it.
"""

import pytest

from lca.infrastructure.capability.search.search import SearchService
from lca.infrastructure.search.models.models import SearchHit, SearchResponse
from lca.infrastructure.tools.web_search import WebSearchExecutor


def _ok_response() -> SearchResponse:
    return SearchResponse(
        query="q",
        provider="fake",
        results=(SearchHit(title="T", url="https://example.test/x", content="c"),),
    )


def _definition_executor() -> WebSearchExecutor:
    async def fake_provider(query: str, **kwargs) -> SearchResponse:
        return _ok_response()

    service = SearchService()
    service.register("fake", fake_provider)
    return WebSearchExecutor(search=service)


@pytest.mark.asyncio
async def test_dispatch_uses_definition_seam_when_search_service_provided():
    obs = await _definition_executor().search({"query": "q"})
    assert obs.success is True
    assert obs.extra["search_seam"] == "definition"
    assert obs.payload["provider"] == "fake"


@pytest.mark.asyncio
async def test_dispatch_uses_ambient_seam_when_search_service_missing(monkeypatch):
    async def fake_ambient(query: str, **kwargs) -> SearchResponse:
        return _ok_response()

    monkeypatch.setattr("lca.infrastructure.tools.web_search.web_search", fake_ambient)
    obs = await WebSearchExecutor(search=None).search({"query": "q"})
    assert obs.success is True
    assert obs.extra["search_seam"] == "ambient"


@pytest.mark.asyncio
async def test_ambient_failure_carries_seam_tag(monkeypatch):
    async def fake_ambient(query: str, **kwargs) -> SearchResponse:
        return SearchResponse(query="q", provider="", error="no search providers configured")

    monkeypatch.setattr("lca.infrastructure.tools.web_search.web_search", fake_ambient)
    obs = await WebSearchExecutor(search=None).search({"query": "q"})
    assert obs.success is False
    assert obs.extra["search_seam"] == "ambient"
    assert "no search providers" in (obs.error or "")
