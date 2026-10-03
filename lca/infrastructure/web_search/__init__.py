"""Web-search channel: Muse-aligned 3-tier browser search routing.

Tiers, lightest first:

    SEARCH (text search, source discovery)
      -> FETCH (httpx page fetch + text extraction)
      -> BROWSE (playwright real browser: JS rendering / login / interaction)

Honest verdict: tier-1 success = SEARCHED (found); only tier-2/3 holding the
original page text = VERIFIED. Live ``vertical`` channels (weather/datetime)
hit the data source directly, so their results are VERIFIED.

Quick start:

    from lca.infrastructure.web_search import (
        SearchRouter, SearchRequest, DuckDuckGoProvider,
    )
    from lca.infrastructure.web_search.verticals import build_default_handlers

    router = SearchRouter(
        search_provider=DuckDuckGoProvider(),
        vertical_handlers=build_default_handlers(),
    )
    outcome = router.run(SearchRequest(query="...", need_text=True))
    print(outcome.verdict, outcome.tier_reached)
    for c in outcome.citations:
        print(c.render())  # line-numbered citation mark
"""

from lca.contracts.models.cognition.web_search import (
    Citation,
    SearchOutcome,
    SearchRequest,
    SearchResult,
    SearchTier,
    Verdict,
    Vertical,
)
from lca.infrastructure.web_search.browser import BrowserBackend, BrowserMode
from lca.infrastructure.web_search.errors import (
    FeatureUnavailableError,
    FetchError,
    ProviderError,
    ProviderNotConfiguredError,
    WebSearchError,
)
from lca.infrastructure.web_search.fetch import FetchResult, fetch_text
from lca.infrastructure.web_search.providers import DuckDuckGoProvider, SearchProvider
from lca.infrastructure.web_search.router import SearchRouter
from lca.infrastructure.web_search.verticals import build_default_handlers

__all__ = [
    "BrowserBackend",
    "BrowserMode",
    "Citation",
    "DuckDuckGoProvider",
    "FeatureUnavailableError",
    "FetchError",
    "FetchResult",
    "ProviderError",
    "ProviderNotConfiguredError",
    "SearchOutcome",
    "SearchProvider",
    "SearchRequest",
    "SearchResult",
    "SearchRouter",
    "SearchTier",
    "Verdict",
    "Vertical",
    "WebSearchError",
    "build_default_handlers",
    "fetch_text",
]
