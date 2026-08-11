"""Search intent detection + LLM native fallback routing."""

from __future__ import annotations

from typing import Any

from lca.layer0_infra.llm_adapter.settings import get_llm_settings
from lca.layer0_infra.search.constants import SEARCH_INTENT_PATTERNS
from lca.layer0_infra.search.scope import get_search_run_state, should_prefer_llm_search
from lca.layer0_infra.search.service import any_search_provider_available
from lca.layer0_infra.search.settings import get_search_settings


def is_search_intent(text: str) -> bool:
    lowered = (text or "").lower()
    if not lowered.strip():
        return False
    return any(pattern in lowered for pattern in SEARCH_INTENT_PATTERNS)


def resolve_llm_search_kwargs(*, task: str) -> dict[str, Any]:
    """Extra kwargs for LLM calls when Qwen native search should act as fallback.

    Enabled when:
    - ``LLM_ENABLE_SEARCH`` is true AND task looks search-like, OR
    - a prior ``web_search`` tool attempt failed this run, OR
    - no Tavily API key but search intent detected (primary path).
    """
    llm_cfg = get_llm_settings()
    search_cfg = get_search_settings()
    if not search_cfg.llm_fallback:
        return {}

    state = get_search_run_state()
    search_like = is_search_intent(task)
    tavily_ready = any_search_provider_available()

    enable = False
    if (
        (should_prefer_llm_search() and llm_cfg.enable_search)
        or (search_like and llm_cfg.enable_search and not tavily_ready)
        or (search_like and state.web_search_failed and llm_cfg.enable_search)
    ):
        enable = True

    if not enable:
        return {}

    extra: dict[str, Any] = {"enable_search": True}
    if (search_like and llm_cfg.forced_search) or search_like:
        extra["search_options"] = {"forced_search": True}
    return extra


def search_routing_hint(*, tavily_available: bool) -> str:
    """Prompt block injected into agent templates (LobeHub lobe-web-browsing parity)."""
    if tavily_available:
        return (
            "- 实时信息/新闻：直接 **use_tool → web_search**（等同 LobeHub Web Browsing）。\n"
            "- 勿对实时搜索使用 search_skill / import_skill（尤其 Tavily CLI skill）。\n"
            "- 勿在沙箱安装 tvly CLI 或 curl 安装脚本。\n"
            "- web_search 失败时 **respond**，系统将启用 LLM 联网搜索兜底。"
        )
    return (
        "- 实时信息/新闻：优先 **respond**（系统将启用 Qwen 联网搜索兜底）。\n"
        "- 勿 search_skill 安装 Tavily CLI；勿沙箱 curl tvly。\n"
        "- 配置 TAVILY_API_KEY 后应改用 **web_search** 工具。"
    )
