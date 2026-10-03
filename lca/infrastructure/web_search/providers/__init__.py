"""通用搜索 providers."""

from lca.infrastructure.web_search.providers.base import SearchProvider
from lca.infrastructure.web_search.providers.duckduckgo import DuckDuckGoProvider

__all__ = ["DuckDuckGoProvider", "SearchProvider"]
