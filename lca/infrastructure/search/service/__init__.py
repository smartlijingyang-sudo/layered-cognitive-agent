"""Public exports for ``service`` (auto-fixed)."""

from lca.infrastructure.search.service.service import (
    any_search_provider_available,
    web_search,
    format_search_content,
    build_search_plugin_state,
)

__all__ = ['any_search_provider_available', 'web_search', 'format_search_content', 'build_search_plugin_state']
