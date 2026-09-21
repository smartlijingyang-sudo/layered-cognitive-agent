"""Search intent detection + LLM native fallback routing."""

from __future__ import annotations

import re
from typing import Any

from lca.infrastructure.llm_adapter.settings.settings import get_llm_settings
from lca.infrastructure.search.constants.constants import (
    FRESHNESS_VERBS,
    SEARCH_INTENT_PATTERNS,
    TEMPORAL_YEAR_REGEX,
)
from lca.infrastructure.search.scope.scope import get_search_run_state, should_prefer_llm_search
from lca.infrastructure.search.service.service import any_search_provider_available
from lca.infrastructure.search.settings.settings import get_search_settings

_YEAR_RE = re.compile(TEMPORAL_YEAR_REGEX)


def is_search_intent(text: str) -> bool:
    """Detect whether query requires web search / real-time freshness."""
    lowered = (text or "").lower()
    if not lowered.strip():
        return False
    if any(pattern in lowered for pattern in SEARCH_INTENT_PATTERNS):
        return True
    if _YEAR_RE.search(lowered) and any(verb in lowered for verb in FRESHNESS_VERBS):
        return True
    return False


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


def search_routing_hint(
    *,
    tavily_available: bool | None = None,
    search_available: bool | None = None,
) -> str:
    """Prompt block injected into agent templates (Grok Freshness-First & LobeHub parity)."""
    ready = (
        search_available
        if search_available is not None
        else (tavily_available if tavily_available is not None else any_search_provider_available())
    )
    if ready:
        return (
            "- **时效性与检索第一原则 (Freshness-First)**:\n"
            "  - 始终以系统提供的 CURRENT_DATE 作为当前时间基准。\n"
            "  - 当任务涉及实时事件、最新动态、近期数据，或信息可能在模型知识截止期后发生演变时"
            "（如开源类库版本更新、API 变更、Changelog、CVE 漏洞、官方文档更新），"
            "**必须优先调用 search (web_search)**，严禁依赖参数化记忆猜测或生成未经检索核实的内容。\n"
            "  - **高质量检索构造**: 结合 CURRENT_DATE 主动添加时间限定（如年份 2026、月份），"
            "若搜索强时效/今日新闻，建议传递可选参数 time_range='day' 或 'week'。\n"
            "  - 勿对实时搜索使用 search_skill / import_skill（尤其 Tavily CLI skill）；勿沙箱 curl 安装脚本。\n"
            "  - web_search 失败或无返回时 **respond** 纯文本说明情况，系统将自动启用 LLM 联网搜索兜底。"
        )
    return (
        "- **时效性与检索提示 (Freshness Hint)**:\n"
        "  - 当前外部搜索 Provider 未配置，涉及实时/最新信息时请直接 **respond**（系统将启用 LLM 联网搜索兜底）。\n"
        "  - 勿 search_skill 安装 Tavily CLI；勿沙箱 curl tvly。\n"
        "  - 配置 EXA_API_KEY / SEARXNG_URL / TAVILY_API_KEY 后将自动启用原生 **web_search** 高速检索。"
    )
