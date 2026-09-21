"""Unit tests for refactored multi-provider Search Service."""

from unittest.mock import AsyncMock, patch

import pytest

from lca.infrastructure.search.constants.constants import (
    PROVIDER_EXA,
    PROVIDER_SEARXNG,
)
from lca.infrastructure.search.models.models import SearchHit, SearchResponse
from lca.infrastructure.search.service.service import any_search_provider_available, web_search


@pytest.mark.asyncio
async def test_search_service_fallback_chain():
    """Verify web_search falls back gracefully across configured providers."""
    # 1. Exa fails -> fallback to SearXNG
    with (
        patch(
            "lca.infrastructure.search.providers.exa.search_exa",
            new_callable=AsyncMock,
        ) as mock_exa,
        patch(
            "lca.infrastructure.search.providers.searxng.search_searxng",
            new_callable=AsyncMock,
        ) as mock_searx,
        patch(
            "lca.infrastructure.search.service.service.configured_provider_ids",
            return_value=(PROVIDER_EXA, PROVIDER_SEARXNG),
        ),
        patch(
            "lca.infrastructure.search.providers.exa.exa_api_key_configured",
            return_value=True,
        ),
        patch(
            "lca.infrastructure.search.providers.searxng.searxng_available",
            return_value=True,
        ),
    ):
        mock_exa.return_value = SearchResponse(
            query="test", provider=PROVIDER_EXA, error="429 quota exhausted"
        )
        mock_searx.return_value = SearchResponse(
            query="test",
            provider=PROVIDER_SEARXNG,
            results=(SearchHit(title="Local Result", url="http://local.test", content="content"),),
        )

        res = await web_search("test")
        assert res.ok
        assert res.provider == PROVIDER_SEARXNG
        assert len(res.results) == 1
        assert res.results[0].title == "Local Result"

        mock_exa.assert_awaited_once()
        mock_searx.assert_awaited_once()


def test_any_search_provider_available():
    with (
        patch(
            "lca.infrastructure.search.service.service.configured_provider_ids",
            return_value=(PROVIDER_EXA, PROVIDER_SEARXNG),
        ),
        patch(
            "lca.infrastructure.search.providers.exa.exa_api_key_configured",
            return_value=False,
        ),
        patch(
            "lca.infrastructure.search.providers.searxng.searxng_available",
            return_value=True,
        ),
    ):
        assert any_search_provider_available() is True


@pytest.mark.asyncio
async def test_search_exa_time_range_filter():
    from unittest.mock import MagicMock

    from lca.infrastructure.search.providers.exa import search_exa

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "results": [
            {"title": "Fresh Post", "url": "https://example.com/fresh", "highlights": ["news"]}
        ]
    }
    mock_resp.raise_for_status = MagicMock()

    captured_payload = {}

    async def fake_post(url, json=None, headers=None):
        nonlocal captured_payload
        captured_payload = json
        return mock_resp

    from lca.infrastructure.search.settings.settings import SearchSettings

    settings = SearchSettings(exa_api_key="mock-key")
    with patch("httpx.AsyncClient.post", side_effect=fake_post):
        res = await search_exa("latest news", time_range="day", settings=settings)
        assert res.ok
        assert "startPublishedDate" in captured_payload
        assert len(res.results) == 1
        assert res.results[0].title == "Fresh Post"


def test_search_provider_protocol_and_registry():
    """Verify built-in providers implement SearchProvider and register properly."""
    from lca.infrastructure.search.providers.exa import ExaSearchProvider
    from lca.infrastructure.search.providers.protocol import SearchProvider
    from lca.infrastructure.search.providers.registry import (
        SearchProviderRegistry,
        get_search_provider,
    )
    from lca.infrastructure.search.providers.searxng import SearXNGSearchProvider
    from lca.infrastructure.search.providers.tavily import TavilySearchProvider

    exa = ExaSearchProvider()
    searx = SearXNGSearchProvider()
    tavily = TavilySearchProvider()

    assert isinstance(exa, SearchProvider)
    assert isinstance(searx, SearchProvider)
    assert isinstance(tavily, SearchProvider)

    # Test default registry lookup
    assert get_search_provider("exa") is not None
    assert get_search_provider("searxng") is not None
    assert get_search_provider("tavily") is not None
    assert get_search_provider("non_existent") is None

    # Custom registry isolated test
    custom_reg = SearchProviderRegistry()
    assert custom_reg.all_providers() == ()
    custom_reg.register(exa)
    assert custom_reg.get("exa") is exa
    assert len(custom_reg.all_providers()) == 1
