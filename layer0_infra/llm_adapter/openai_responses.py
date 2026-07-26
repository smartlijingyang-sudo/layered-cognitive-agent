"""OpenAI Responses API 适配器（基于 AsyncOpenAI）。

依赖:
    pip install "openai>=1.40"

环境变量:
    OPENAI_API_KEY（或在构造时显式传入）
"""

from __future__ import annotations

from typing import Any, Optional

from openai import AsyncOpenAI


class OpenAIResponsesAdapter:
    """
    用 client.responses.create(...) 实现 LLMAdapter.complete。

    - kwargs 透传给 responses.create（temperature / tools / reasoning 等）。
    - 优先取 response.output_text；SDK 版本没有该便捷属性时，手动从
      response.output 里拼出 message 类型 item 的 output_text。
    """

    def __init__(
        self,
        client: Optional[AsyncOpenAI] = None,
        model: str = "gpt-4.1",
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_kwargs: Optional[dict[str, Any]] = None,
    ) -> None:
        self._client = client or AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._default_kwargs = default_kwargs or {}

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        params = {**self._default_kwargs, **kwargs}
        model = params.pop("model", self._model)

        response = await self._client.responses.create(
            model=model,
            input=prompt,
            **params,
        )

        text = getattr(response, "output_text", None)
        if text:
            return text

        chunks: list[str] = []
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", None) == "message":
                for content in getattr(item, "content", []) or []:
                    if getattr(content, "type", None) == "output_text":
                        chunks.append(content.text)
        return "".join(chunks)
