"""Housekeeper AsyncOpenAI client — OpenAI-compat face only."""

from __future__ import annotations

from typing import Any

from lca.layer0_infra.llm.config import LLMFace, resolve_endpoint
from lca.layer0_infra.llm_errors import LLMUnavailableError

_cached_async_client: Any = None
_cached_client_key: tuple[str | None, str | None] | None = None


def get_async_openai_client() -> Any:
    """管家面客户端：只打 OpenAI 兼容口，不打 agent 的 Anthropic Messages 口。"""
    global _cached_async_client, _cached_client_key
    endpoint = resolve_endpoint(LLMFace.OPENAI_COMPAT)
    if not endpoint.base_url:
        raise LLMUnavailableError(
            "LLM_OPENAI_BASE_URL 未配置。管家面（标题 / generateObject / embeddings）"
            "需要 OpenAI 兼容口；agent 的 LLM_BASE_URL 是 Anthropic Messages，"
            "不能拼 /chat/completions。"
        )
    cache_key = (endpoint.api_key or None, endpoint.base_url)
    if _cached_async_client is not None and _cached_client_key == cache_key:
        return _cached_async_client
    from openai import AsyncOpenAI

    _cached_async_client = AsyncOpenAI(api_key=endpoint.api_key or None, base_url=endpoint.base_url)
    _cached_client_key = cache_key
    return _cached_async_client


def reset_async_openai_client() -> None:
    """测试用：丢掉缓存的管家客户端。"""
    global _cached_async_client, _cached_client_key
    _cached_async_client = None
    _cached_client_key = None
