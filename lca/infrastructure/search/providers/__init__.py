"""Search providers registry and adapters."""

from lca.infrastructure.search.providers.exa import (
    ExaSearchProvider,
    exa_api_key_configured,
    search_exa,
)
from lca.infrastructure.search.providers.protocol import SearchProvider
from lca.infrastructure.search.providers.registry import (
    SearchProviderRegistry,
    default_search_provider_registry,
    get_search_provider,
    register_search_provider,
)
from lca.infrastructure.search.providers.searxng import (
    SearXNGSearchProvider,
    search_searxng,
    searxng_available,
)
from lca.infrastructure.search.providers.tavily import (
    TavilySearchProvider,
    search_tavily,
    tavily_api_key_configured,
)

# Register default standard providers
register_search_provider(ExaSearchProvider())
register_search_provider(SearXNGSearchProvider())
register_search_provider(TavilySearchProvider())

__all__ = [
    "ExaSearchProvider",
    "SearXNGSearchProvider",
    "SearchProvider",
    "SearchProviderRegistry",
    "TavilySearchProvider",
    "default_search_provider_registry",
    "exa_api_key_configured",
    "get_search_provider",
    "register_search_provider",
    "search_exa",
    "search_searxng",
    "search_tavily",
    "searxng_available",
    "tavily_api_key_configured",
]
