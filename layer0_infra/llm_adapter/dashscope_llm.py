"""DashScope LLM 适配器（OpenAI 兼容模式）。

DashScope 的 OpenAI 兼容接口走 chat/completions，不是 responses API，
因此用 client.chat.completions.create() 实现 LLMAdapter.complete。

依赖:
    pip install "openai>=1.40" python-dotenv

环境变量（或在 .env 文件中配置）:
    LLM_API_KEY   DashScope API Key
    LLM_BASE_URL  https://dashscope.aliyuncs.com/compatible-mode/v1
    LLM_MODEL     qwen-plus（默认）
"""

from __future__ import annotations

import os
from typing import Any, Optional

from openai import AsyncOpenAI


class DashScopeLLMAdapter:
    """
    通过 DashScope OpenAI 兼容接口调用通义千问系列模型。
    接口签名与 MockLLMAdapter 完全一致，Brain 层无需感知差异。
    """

    def __init__(
        self,
        model: Optional[str] = None,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self._model = model or os.getenv("LLM_MODEL", "qwen-plus")
        self._api_key = api_key or os.getenv("LLM_API_KEY", "")
        self._base_url = base_url or os.getenv(
            "LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self._client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        model = kwargs.pop("model", self._model)
        temperature = kwargs.pop("temperature", 0.7)
        max_tokens = kwargs.pop("max_tokens", 2048)

        response = await self._client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        return response.choices[0].message.content or ""
