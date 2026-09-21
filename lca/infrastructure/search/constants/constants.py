"""Unified search plane — provider identifiers and routing constants."""

from __future__ import annotations

PROVIDER_EXA = "exa"
PROVIDER_SEARXNG = "searxng"
PROVIDER_TAVILY = "tavily"
PROVIDER_LLM_NATIVE = "llm_native"

DEFAULT_SEARCH_PROVIDERS: tuple[str, ...] = (
    PROVIDER_EXA,
    PROVIDER_SEARXNG,
    PROVIDER_TAVILY,
)

# LobeHub wire identifier for web browsing builtin.
LOBE_WEB_BROWSING_ID = "lobe-web-browsing"
WEB_BROWSING_API_SEARCH = "search"

WEB_SEARCH_TOOL = "search"

# Heuristic patterns for search-intent routing (news / realtime / lookup).
SEARCH_INTENT_PATTERNS: tuple[str, ...] = (
    # Real-time news & temporal markers
    "新闻",
    "资讯",
    "头条",
    "今天",
    "最新",
    "实时",
    "近期",
    "最近",
    "昨天",
    "上周",
    "本周",
    "本月",
    "今年",
    "搜索",
    "查一下",
    "帮我找",
    "查询",
    # Evolving software & versions (Grok freshness heuristics)
    "最新版",
    "新版",
    "新特性",
    "更新日志",
    "更新说明",
    "版本更新",
    "changelog",
    "release note",
    "release notes",
    "what's new",
    "breaking change",
    "breaking changes",
    # English temporal & lookup
    "what's the news",
    "latest news",
    "today's news",
    "current events",
    "web search",
    "look up",
    "search for",
    "recent updates",
    "latest release",
    "current status",
)

# Regex for matching 4-digit years (e.g. 2024, 2026, 2030)
TEMPORAL_YEAR_REGEX = r"\b(20\d{2})\b"
FRESHNESS_VERBS: tuple[str, ...] = (
    "version",
    "release",
    "releases",
    "api",
    "doc",
    "docs",
    "status",
    "news",
    "update",
    "updates",
    "版本",
    "发布",
    "更新",
    "文档",
    "现状",
    "进展",
    "怎样",
    "如何",
)

NEWS_TOPIC_HINTS: tuple[str, ...] = (
    "新闻",
    "资讯",
    "头条",
    "news",
    "today",
    "今天",
)
