"""Public exports for ``router`` (auto-fixed)."""

from lca.infrastructure.search.router.router import (
    is_search_intent,
    resolve_llm_search_kwargs,
    search_routing_hint,
)

__all__ = ['is_search_intent', 'resolve_llm_search_kwargs', 'search_routing_hint']
