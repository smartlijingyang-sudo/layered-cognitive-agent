"""Search plane — unified web search replacing LobeHub server SearchService."""

from lca.layer0_infra.search.constants import (
    LOBE_WEB_BROWSING_ID,
    PROVIDER_LLM_NATIVE,
    PROVIDER_TAVILY,
    WEB_BROWSING_API_SEARCH,
    WEB_SEARCH_TOOL,
)
from lca.layer0_infra.search.router import (
    is_search_intent,
    resolve_llm_search_kwargs,
    search_routing_hint,
)
from lca.layer0_infra.search.scope import search_run_scope
from lca.layer0_infra.search.service import any_search_provider_available, web_search
from lca.layer0_infra.search.settings import get_search_settings

__all__ = [
    "LOBE_WEB_BROWSING_ID",
    "PROVIDER_LLM_NATIVE",
    "PROVIDER_TAVILY",
    "WEB_BROWSING_API_SEARCH",
    "WEB_SEARCH_TOOL",
    "any_search_provider_available",
    "get_search_settings",
    "is_search_intent",
    "resolve_llm_search_kwargs",
    "search",
    "search_routing_hint",
    "search_run_scope",
    "web_search",
]
