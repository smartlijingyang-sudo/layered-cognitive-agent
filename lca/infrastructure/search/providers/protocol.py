"""SearchProvider Port / Domain Protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from lca.infrastructure.search.models.models import SearchResponse
    from lca.infrastructure.search.settings.settings import SearchSettings


@runtime_checkable
class SearchProvider(Protocol):
    """Protocol for external web search providers (Exa, SearXNG, Tavily, etc.)."""

    @property
    def id(self) -> str:
        """Provider identifier matching constants (e.g. 'exa', 'searxng', 'tavily')."""
        ...

    def is_available(self, settings: SearchSettings | None = None) -> bool:
        """Check if provider is configured and available."""
        ...

    async def search(
        self,
        query: str,
        *,
        topic: str | None = None,
        time_range: str | None = None,
        settings: SearchSettings | None = None,
    ) -> SearchResponse:
        """Execute web search and return standard SearchResponse."""
        ...
