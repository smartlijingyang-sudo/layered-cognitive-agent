"""SearchProvider Registry — Open-Closed provider management."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lca.infrastructure.search.providers.protocol import SearchProvider


class SearchProviderRegistry:
    """Registry mapping provider ID to SearchProvider implementations."""

    def __init__(self) -> None:
        self._providers: dict[str, SearchProvider] = {}

    def register(self, provider: SearchProvider) -> None:
        """Register a search provider."""
        self._providers[provider.id] = provider

    def get(self, provider_id: str) -> SearchProvider | None:
        """Look up provider by ID."""
        return self._providers.get(provider_id)

    def all_providers(self) -> tuple[SearchProvider, ...]:
        """Return all registered providers."""
        return tuple(self._providers.values())

    def clear(self) -> None:
        """Clear all registered providers (for testing)."""
        self._providers.clear()


default_search_provider_registry = SearchProviderRegistry()


def get_search_provider(provider_id: str) -> SearchProvider | None:
    """Convenience getter for default registry."""
    return default_search_provider_registry.get(provider_id)


def register_search_provider(provider: SearchProvider) -> None:
    """Convenience registration on default registry."""
    default_search_provider_registry.register(provider)
