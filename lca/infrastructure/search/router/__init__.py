"""Public exports for ``router`` (auto-fixed)."""

from lca.infrastructure.search.router.router import (
    get_llm_settings,
    is_search_intent,
    resolve_llm_search_kwargs,
    search_routing_hint,
)

__all__ = [
    'get_llm_settings',
    'is_search_intent',
    'resolve_llm_search_kwargs',
    'search_routing_hint',
]
