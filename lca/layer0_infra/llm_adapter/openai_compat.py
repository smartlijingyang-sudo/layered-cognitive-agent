"""通用 OpenAI 兼容 LLM 适配器。

支持所有 OpenAI chat/completions 兼容 API：
  - OpenAI (api.openai.com)
  - DashScope / 通义千问 (dashscope.aliyuncs.com/compatible-mode)
  - Ollama, vLLM, LiteLLM 等

只需配置环境变量即可切换，代码无需改动：
  LLM_API_KEY   API Key
  LLM_BASE_URL  基地址（默认 https://api.openai.com/v1）
  LLM_MODEL     模型名（默认 gpt-4.1）

依赖: pip install "openai>=1.40"
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

from lca.contracts.protocols import LLMAdapter

_DEFAULT_TEMPERATURE = 0.7
_DEFAULT_MAX_TOKENS = 2048


class OpenAICompatAdapter(LLMAdapter):
    """实现 LLMAdapter 协议。走 client.chat.completions.create()。"""

    name = "openai-compat"
    _client: Any

    def __init__(
        self,
        model: str | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        from openai import AsyncOpenAI

        self._model: str = model if model is not None else os.getenv("LLM_MODEL", "gpt-4.1")
        self._client = AsyncOpenAI(
            api_key=api_key or os.getenv("LLM_API_KEY", ""),
            base_url=base_url or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        )

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        response = await self._client.chat.completions.create(
            model=kwargs.pop("model", self._model),
            messages=[{"role": "user", "content": prompt}],
            temperature=kwargs.pop("temperature", _DEFAULT_TEMPERATURE),
            max_tokens=kwargs.pop("max_tokens", _DEFAULT_MAX_TOKENS),
            **kwargs,
        )
        return response.choices[0].message.content or ""

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        raise NotImplementedError("流式输出暂未实现")
        yield ""  # pragma: no cover
