"""Unit tests for refactored multi-provider Search Service."""

import pytest
from unittest.mock import AsyncMock, patch

from lca.infrastructure.search.constants.constants import (
    PROVIDER_EXA,
    PROVIDER_SEARXNG,
    PROVIDER_TAVILY,
)
from lca.infrastructure.search.models.models import SearchHit, SearchResponse
from lca.infrastructure.search.service.service import web_search, any_search_provider_available


@pytest.mark.asyncio
async def test_search_service_fallback_chain():
    """Verify web_search falls back gracefully across configured providers."""
    # 1. Exa fails -> fallback to SearXNG
    with (
        patch(
            "lca.infrastructure.search.service.service.search_exa",
            new_callable=AsyncMock,
        ) as mock_exa,
        patch(
            "lca.infrastructure.search.service.service.search_searxng",
            new_callable=AsyncMock,
        ) as mock_searx,
        patch(
            "lca.infrastructure.search.service.service.configured_provider_ids",
            return_value=(PROVIDER_EXA, PROVIDER_SEARXNG),
        ),
        patch(
            "lca.infrastructure.search.service.service.exa_api_key_configured",
            return_value=True,
        ),
        patch(
            "lca.infrastructure.search.service.service.searxng_available",
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
    with patch(
        "lca.infrastructure.search.service.service.configured_provider_ids",
        return_value=(PROVIDER_EXA, PROVIDER_SEARXNG),
    ), patch(
        "lca.infrastructure.search.service.service.exa_api_key_configured",
        return_value=False,
    ), patch(
        "lca.infrastructure.search.service.service.searxng_available",
        return_value=True,
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
