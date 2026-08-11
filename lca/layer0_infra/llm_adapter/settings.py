"""LLM 生成参数配置 —— pydantic-settings 驱动（env 前缀 LLM_，读 .env）。

覆盖 OpenAI 兼容通用采样参数 + 百炼/Qwen 扩展（思考、联网搜索、并行工具调用）。
非 OpenAI 标准字段经 ``extra_body`` 注入，避免 SDK 校验拒绝。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 与百炼 Qwen3 推荐对齐的生成默认值
DEFAULT_TEMPERATURE = 0.6
DEFAULT_TOP_P = 0.95
DEFAULT_TOP_K = 20
DEFAULT_MAX_TOKENS = 4096
# 有 function-calling 时默认给更大输出预算，降低 tool arguments 被截断概率（ADR-0047）
DEFAULT_MAX_TOKENS_WITH_TOOLS = 8192
DEFAULT_SEARCH_STRATEGY = "turbo"
_QWEN_MODEL_PREFIX = "qwen"


class LLMSettings(BaseSettings):
    """LLM 调用侧可配置参数（不含凭证；凭证仍走工厂/适配器显式参数）。

    环境变量示例::

        LLM_TEMPERATURE=0.6
        LLM_TOP_P=0.95
        LLM_TOP_K=20
        LLM_MAX_TOKENS=4096
        LLM_PARALLEL_TOOL_CALLS=true
        LLM_ENABLE_THINKING=true
        LLM_ENABLE_SEARCH=false
        LLM_SEARCH_STRATEGY=max
        LLM_FORCED_SEARCH=false
        LLM_ENABLE_SOURCE=true
        LLM_ENABLE_CITATION=true
        LLM_REPETITION_PENALTY=1.05
        LLM_PRESENCE_PENALTY=0
        LLM_FREQUENCY_PENALTY=0
        LLM_SEED=42
    """

    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    temperature: float = Field(default=DEFAULT_TEMPERATURE, ge=0.0, lt=2.0)
    top_p: float | None = Field(default=DEFAULT_TOP_P, gt=0.0, le=1.0)
    # None = 不注入；Qwen 模型在 builder 中回落 DEFAULT_TOP_K
    top_k: int | None = Field(default=None, ge=0)
    max_tokens: int = Field(default=DEFAULT_MAX_TOKENS, ge=1)
    seed: int | None = None
    presence_penalty: float | None = Field(default=None, ge=-2.0, le=2.0)
    frequency_penalty: float | None = Field(default=None, ge=-2.0, le=2.0)
    repetition_penalty: float | None = Field(default=None, gt=0.0)

    # 工具调用
    parallel_tool_calls: bool = True
    tool_choice: str | None = "auto"  # auto | none | required（对象形态由调用方 kwargs 覆盖）

    # 百炼 / Qwen 扩展（None = 不注入；无 tools 时 enable_thinking 默认 True）
    enable_thinking: bool | None = None
    enable_search: bool | None = None
    search_strategy: str | None = None  # turbo | max | agent | agent_max
    forced_search: bool | None = None
    enable_source: bool | None = None
    enable_citation: bool | None = None
    citation_format: str | None = None
    search_top_k: int | None = Field(default=None, ge=1)
    freshness: str | None = None  # 7 | 30 | 180 | 365


@lru_cache(maxsize=1)
def get_llm_settings() -> LLMSettings:
    """进程内缓存的默认设置（测试可 clear）。"""
    return LLMSettings()


def clear_llm_settings_cache() -> None:
    get_llm_settings.cache_clear()


def is_qwen_model(model: str) -> bool:
    return model.strip().lower().startswith(_QWEN_MODEL_PREFIX)


def _omit_none(mapping: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in mapping.items() if v is not None}


def _build_search_options(
    *,
    enable_search: bool | None,
    search_strategy: str | None,
    forced_search: bool | None,
    enable_source: bool | None,
    enable_citation: bool | None,
    citation_format: str | None,
    search_top_k: int | None,
    freshness: str | None,
) -> dict[str, Any] | None:
    strategy = search_strategy
    if enable_search and strategy is None:
        strategy = DEFAULT_SEARCH_STRATEGY
    options = _omit_none(
        {
            "search_strategy": strategy,
            "forced_search": forced_search,
            "enable_source": enable_source,
            "enable_citation": enable_citation,
            "citation_format": citation_format,
            "search_top_k": search_top_k,
            "freshness": freshness,
        }
    )
    return options or None


def build_generation_kwargs(
    *,
    model: str,
    has_tools: bool,
    call_kwargs: dict[str, Any],
    settings: LLMSettings | None = None,
) -> dict[str, Any]:
    """合并 settings 默认值与调用方 kwargs，产出可交给 OpenAI SDK 的生成参数。

    - OpenAI 标准字段放顶层；
    - 百炼扩展（enable_thinking / enable_search / search_options / top_k /
      repetition_penalty）放入 ``extra_body``；
    - 调用方显式传入的同名键覆盖 settings；
    - 调用方已有 ``extra_body`` 时与默认扩展浅合并（调用方优先）。
    """
    cfg = settings if settings is not None else get_llm_settings()
    remaining = dict(call_kwargs)

    caller_extra = remaining.pop("extra_body", None)
    if caller_extra is not None and not isinstance(caller_extra, dict):
        caller_extra = None

    temperature = remaining.pop("temperature", cfg.temperature)
    top_p = remaining.pop("top_p", cfg.top_p)
    # 调用方显式 max_tokens 优先；否则有 tools 时抬高默认预算
    if "max_tokens" in remaining:
        max_tokens = remaining.pop("max_tokens")
    elif has_tools and cfg.max_tokens == DEFAULT_MAX_TOKENS:
        max_tokens = DEFAULT_MAX_TOKENS_WITH_TOOLS
    else:
        max_tokens = cfg.max_tokens
    seed = remaining.pop("seed", cfg.seed)
    presence_penalty = remaining.pop("presence_penalty", cfg.presence_penalty)
    frequency_penalty = remaining.pop("frequency_penalty", cfg.frequency_penalty)
    parallel_tool_calls = remaining.pop("parallel_tool_calls", cfg.parallel_tool_calls)
    tool_choice = remaining.pop("tool_choice", cfg.tool_choice)
    stop = remaining.pop("stop", None)

    top_k = remaining.pop("top_k", cfg.top_k)
    repetition_penalty = remaining.pop("repetition_penalty", cfg.repetition_penalty)
    enable_thinking = remaining.pop("enable_thinking", cfg.enable_thinking)
    enable_search = remaining.pop("enable_search", cfg.enable_search)
    search_options = remaining.pop("search_options", None)

    qwen = is_qwen_model(model)
    # LCA now uses native tool_calls (not Decision JSON), so reasoning_content
    # and tool_calls are independent channels — safe to enable thinking with tools.
    if enable_thinking is None and qwen:
        enable_thinking = True
    if top_k is None and qwen:
        top_k = DEFAULT_TOP_K

    api_kwargs: dict[str, Any] = {
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if top_p is not None:
        api_kwargs["top_p"] = top_p
    if seed is not None:
        api_kwargs["seed"] = seed
    if presence_penalty is not None:
        api_kwargs["presence_penalty"] = presence_penalty
    if frequency_penalty is not None:
        api_kwargs["frequency_penalty"] = frequency_penalty
    if stop is not None:
        api_kwargs["stop"] = stop
    if has_tools:
        api_kwargs["parallel_tool_calls"] = bool(parallel_tool_calls)
        if tool_choice is not None:
            api_kwargs["tool_choice"] = tool_choice

    # 调用方透传的其余未知键（保留兼容）
    api_kwargs.update(remaining)

    extra: dict[str, Any] = {}
    if top_k is not None:
        extra["top_k"] = top_k
    if repetition_penalty is not None:
        extra["repetition_penalty"] = repetition_penalty
    if enable_thinking is not None:
        extra["enable_thinking"] = bool(enable_thinking)
    if enable_search is not None:
        extra["enable_search"] = bool(enable_search)

    if search_options is None:
        search_options = _build_search_options(
            enable_search=enable_search,
            search_strategy=cfg.search_strategy,
            forced_search=cfg.forced_search,
            enable_source=cfg.enable_source,
            enable_citation=cfg.enable_citation,
            citation_format=cfg.citation_format,
            search_top_k=cfg.search_top_k,
            freshness=cfg.freshness,
        )
        # 仅在 enable_search 时附带 search_options，避免无意义字段
        if not enable_search:
            search_options = None
    if search_options is not None:
        extra["search_options"] = search_options

    if caller_extra:
        extra.update(caller_extra)

    if extra:
        api_kwargs["extra_body"] = extra

    return api_kwargs
