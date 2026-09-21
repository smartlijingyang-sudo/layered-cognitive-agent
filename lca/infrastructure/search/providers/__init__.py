"""Search providers registry."""

from lca.infrastructure.search.providers.exa import exa_api_key_configured, search_exa
from lca.infrastructure.search.providers.searxng import search_searxng, searxng_available
from lca.infrastructure.search.providers.tavily import search_tavily, tavily_api_key_configured

__all__ = [
    "exa_api_key_configured",
    "search_exa",
    "search_searxng",
    "search_tavily",
    "searxng_available",
    "tavily_api_key_configured",
]
