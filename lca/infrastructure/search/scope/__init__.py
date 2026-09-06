"""Public exports for ``scope`` (auto-fixed)."""

from lca.infrastructure.search.scope.scope import (
    get_search_run_state,
    reset_search_run_state,
    search_run_scope,
    mark_web_search_attempt,
    should_prefer_llm_search,
)

__all__ = ['get_search_run_state', 'reset_search_run_state', 'search_run_scope', 'mark_web_search_attempt', 'should_prefer_llm_search']
