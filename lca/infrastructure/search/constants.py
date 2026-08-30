"""Unified search plane — provider identifiers and routing constants."""

from __future__ import annotations

PROVIDER_TAVILY = "tavily"
PROVIDER_LLM_NATIVE = "llm_native"

DEFAULT_SEARCH_PROVIDERS: tuple[str, ...] = (PROVIDER_TAVILY,)

# LobeHub wire identifier for web browsing builtin.
LOBE_WEB_BROWSING_ID = "lobe-web-browsing"
WEB_BROWSING_API_SEARCH = "search"

WEB_SEARCH_TOOL = "search"

# Heuristic patterns for search-intent routing (news / realtime / lookup).
SEARCH_INTENT_PATTERNS: tuple[str, ...] = (
    "新闻",
    "资讯",
    "头条",
    "今天",
    "最新",
    "实时",
    "搜索",
    "查一下",
    "帮我找",
    "what's the news",
    "latest news",
    "today's news",
    "current events",
    "web search",
    "look up",
    "search for",
)

NEWS_TOPIC_HINTS: tuple[str, ...] = (
    "新闻",
    "资讯",
    "头条",
    "news",
    "today",
    "今天",
)
