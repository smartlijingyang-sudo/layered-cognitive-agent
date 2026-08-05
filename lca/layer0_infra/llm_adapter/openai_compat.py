"""通用 OpenAI 兼容 LLM 适配器。

支持所有 OpenAI chat/completions 兼容 API。
可观测性由 TelemetryLLMAdapter（组合根包装）负责，本适配器只做 API 调用。
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

from lca.contracts.llm import LLMResponse, TokenUsage
from lca.contracts.protocols import LLMAdapter, Tool

_DEFAULT_TEMPERATURE = 0.7
_DEFAULT_MAX_TOKENS = 2048


def to_openai_tool_spec(tool: Tool) -> dict[str, Any]:
    """将 Tool 协议实例转换为 OpenAI function-calling tool spec。"""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


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

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        tools = kwargs.pop("tools", None)
        api_kwargs: dict[str, Any] = {
            "model": kwargs.pop("model", self._model),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": kwargs.pop("temperature", _DEFAULT_TEMPERATURE),
            "max_tokens": kwargs.pop("max_tokens", _DEFAULT_MAX_TOKENS),
            **kwargs,
        }
        if tools:
            api_kwargs["tools"] = [to_openai_tool_spec(t) for t in tools]

        response = await self._client.chat.completions.create(**api_kwargs)
        msg = response.choices[0].message
        usage = self._extract_usage(response)
        model = getattr(response, "model", "") or self._model

        if msg.tool_calls:
            tc = msg.tool_calls[0]
            text = json.dumps(
                {
                    "action_type": "use_tool",
                    "tool_name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                    "rationale": msg.content or "",
                },
                ensure_ascii=False,
            )
            return LLMResponse(text=text, model=model, usage=usage)
        return LLMResponse(text=msg.content or "", model=model, usage=usage)

    @staticmethod
    def _extract_usage(response: Any) -> TokenUsage | None:
        raw = getattr(response, "usage", None)
        if raw is None:
            return None
        return TokenUsage(
            prompt_tokens=getattr(raw, "prompt_tokens", None),
            completion_tokens=getattr(raw, "completion_tokens", None),
        )

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        raise NotImplementedError("流式输出暂未实现")
        yield ""  # pragma: no cover
