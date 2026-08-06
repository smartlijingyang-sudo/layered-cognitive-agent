"""通用 OpenAI 兼容 LLM 适配器。

支持 Responses API（默认）与 Chat Completions（显式 opt-in）。
可观测性由 TelemetryLLMAdapter（组合根包装）负责，本适配器只做 API 调用。
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent
from lca.contracts.protocols import LLMAdapter
from lca.layer0_infra.llm_adapter.api_style import LLMApiStyle
from lca.layer0_infra.llm_adapter.openai_compat._chat_completions import _ChatCompletionsStrategy
from lca.layer0_infra.llm_adapter.openai_compat._responses import _ResponsesStrategy
from lca.layer0_infra.llm_adapter.openai_compat._strategy import _ApiStrategy

_STRATEGIES: dict[LLMApiStyle, type[Any]] = {
    LLMApiStyle.CHAT_COMPLETIONS: _ChatCompletionsStrategy,
    LLMApiStyle.RESPONSES: _ResponsesStrategy,
}


def _resolve_api_style(api: LLMApiStyle | None) -> LLMApiStyle:
    if api is not None:
        return api
    raw = os.getenv("LLM_API_STYLE", "").strip().lower()
    if raw == LLMApiStyle.CHAT_COMPLETIONS.value:
        return LLMApiStyle.CHAT_COMPLETIONS
    return LLMApiStyle.RESPONSES


class OpenAICompatAdapter(LLMAdapter):
    """实现 LLMAdapter 协议；内部 Strategy 按 ``api`` / ``LLM_API_STYLE`` 选择 wire protocol。"""

    name = "openai-compat"

    def __init__(
        self,
        model: str | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        api: LLMApiStyle | None = None,
    ) -> None:
        from openai import AsyncOpenAI

        self._model: str = model if model is not None else os.getenv("LLM_MODEL", "gpt-4.1")
        client = AsyncOpenAI(
            api_key=api_key or os.getenv("LLM_API_KEY", ""),
            base_url=base_url or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        )
        style = _resolve_api_style(api)
        strategy_cls: type[Any] = _STRATEGIES[style]
        self._strategy: _ApiStrategy = strategy_cls(client, self._model)

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        return await self._strategy.complete(prompt, **kwargs)

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        async for event in self._strategy.stream(prompt, **kwargs):
            yield event
