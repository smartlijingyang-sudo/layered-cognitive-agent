"""Chat Completions API Strategy。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent, TokenUsage
from lca.contracts.protocols import Tool
from lca.layer0_infra.llm_adapter.openai_compat._shared import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    _RawToolCall,
    build_llm_response,
    pick_first_tool_call,
    strip_observability_kwargs,
)


def to_openai_chat_tool_spec(tool: Tool) -> dict[str, Any]:
    """将 Tool 协议实例转换为 Chat Completions function-calling tool spec。"""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


class _ChatCompletionsStrategy:
    def __init__(self, client: Any, default_model: str) -> None:
        self._client = client
        self._model = default_model

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        api_kwargs = self._build_request_kwargs(prompt, **kwargs)
        response = await self._client.chat.completions.create(**api_kwargs)
        msg = response.choices[0].message
        usage = self._extract_usage(response)
        model = getattr(response, "model", "") or self._model
        raw_tc: _RawToolCall | None = None
        text = msg.content or ""
        if msg.tool_calls:
            tc = msg.tool_calls[0]
            raw_tc = _RawToolCall(
                name=tc.function.name,
                arguments_json=tc.function.arguments,
                call_id=tc.id or "",
            )
        return build_llm_response(text=text, tool_call=raw_tc, model=model, usage=usage)

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        api_kwargs = self._build_request_kwargs(prompt, **kwargs)
        api_kwargs["stream"] = True
        api_kwargs["stream_options"] = {"include_usage": True}

        accumulated_text = ""
        tool_calls: dict[int, dict[str, str]] = {}

        stream = await self._client.chat.completions.create(**api_kwargs)
        async for chunk in stream:
            if not chunk.choices:
                usage = self._extract_usage(chunk)
                model = getattr(chunk, "model", "") or self._model
                yield LLMStreamEvent(
                    type=LLMStreamEventType.COMPLETED,
                    response=build_llm_response(
                        text=accumulated_text,
                        tool_call=pick_first_tool_call(tool_calls),
                        model=model,
                        usage=usage,
                    ),
                )
                return

            delta = chunk.choices[0].delta
            if delta.content:
                accumulated_text += delta.content
                yield LLMStreamEvent(
                    type=LLMStreamEventType.OUTPUT_TEXT_DELTA,
                    text=delta.content,
                )

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls:
                        tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
                    entry = tool_calls[idx]
                    name_first = False
                    if tc_delta.id:
                        entry["id"] = tc_delta.id
                    if tc_delta.function and tc_delta.function.name:
                        if not entry["name"]:
                            name_first = True
                        entry["name"] = tc_delta.function.name
                    args_delta = ""
                    if tc_delta.function and tc_delta.function.arguments:
                        args_delta = tc_delta.function.arguments
                        entry["arguments"] += args_delta
                    yield LLMStreamEvent(
                        type=LLMStreamEventType.FUNCTION_CALL_ARGUMENTS_DELTA,
                        tool_call_id=entry["id"] or None,
                        tool_name=entry["name"] if name_first else None,
                        arguments_delta=args_delta,
                    )

    def _build_request_kwargs(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        tools = kwargs.pop("tools", None)
        kwargs = strip_observability_kwargs(kwargs)
        api_kwargs: dict[str, Any] = {
            "model": kwargs.pop("model", self._model),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": kwargs.pop("temperature", DEFAULT_TEMPERATURE),
            "max_tokens": kwargs.pop("max_tokens", DEFAULT_MAX_TOKENS),
            **kwargs,
        }
        if tools:
            api_kwargs["tools"] = [to_openai_chat_tool_spec(t) for t in tools]
        return api_kwargs

    @staticmethod
    def _extract_usage(response: Any) -> TokenUsage | None:
        raw = getattr(response, "usage", None)
        if raw is None:
            return None
        return TokenUsage(
            prompt_tokens=getattr(raw, "prompt_tokens", None),
            completion_tokens=getattr(raw, "completion_tokens", None),
        )
