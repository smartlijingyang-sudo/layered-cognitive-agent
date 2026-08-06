"""Responses API Strategy —— 默认 wire protocol。"""

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
)

_RESPONSE_OUTPUT_TEXT_DELTA = "response.output_text.delta"
_RESPONSE_FUNCTION_ARGS_DELTA = "response.function_call_arguments.delta"
_RESPONSE_COMPLETED = "response.completed"


def to_openai_responses_tool_spec(tool: Tool) -> dict[str, Any]:
    """将 Tool 协议实例转换为 Responses API 扁平 tool spec。"""
    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.parameters,
    }


class _ResponsesStrategy:
    def __init__(self, client: Any, default_model: str) -> None:
        self._client = client
        self._model = default_model

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        api_kwargs = self._build_request_kwargs(prompt, **kwargs)
        response = await self._client.responses.create(**api_kwargs)
        return self._response_to_llm(response, api_kwargs["model"])

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        api_kwargs = self._build_request_kwargs(prompt, **kwargs)
        api_kwargs["stream"] = True

        stream = await self._client.responses.create(**api_kwargs)
        async for event in stream:
            event_type = event.type
            if event_type == _RESPONSE_OUTPUT_TEXT_DELTA:
                yield LLMStreamEvent(
                    type=LLMStreamEventType.OUTPUT_TEXT_DELTA,
                    text=event.delta,
                )
            elif event_type == _RESPONSE_FUNCTION_ARGS_DELTA:
                yield LLMStreamEvent(
                    type=LLMStreamEventType.FUNCTION_CALL_ARGUMENTS_DELTA,
                    tool_call_id=event.item_id,
                    arguments_delta=event.delta,
                )
            elif event_type == _RESPONSE_COMPLETED:
                model = getattr(event.response, "model", "") or self._model
                yield LLMStreamEvent(
                    type=LLMStreamEventType.COMPLETED,
                    response=self._response_to_llm(event.response, model),
                )

    def _build_request_kwargs(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        tools = kwargs.pop("tools", None)
        api_kwargs: dict[str, Any] = {
            "model": kwargs.pop("model", self._model),
            "input": prompt,
            "temperature": kwargs.pop("temperature", DEFAULT_TEMPERATURE),
            "max_output_tokens": kwargs.pop("max_tokens", DEFAULT_MAX_TOKENS),
            **kwargs,
        }
        if tools:
            api_kwargs["tools"] = [to_openai_responses_tool_spec(t) for t in tools]
        return api_kwargs

    def _response_to_llm(self, response: Any, fallback_model: str) -> LLMResponse:
        model = getattr(response, "model", "") or fallback_model
        usage = self._extract_usage(response)
        text = response.output_text or ""
        return build_llm_response(
            text=text,
            tool_call=self._extract_tool_call(response),
            model=model,
            usage=usage,
        )

    @staticmethod
    def _extract_tool_call(response: Any) -> _RawToolCall | None:
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", None) == "function_call":
                return _RawToolCall(
                    name=item.name,
                    arguments_json=item.arguments,
                    call_id=item.call_id or item.id or "",
                )
        return None

    @staticmethod
    def _extract_usage(response: Any) -> TokenUsage | None:
        raw = getattr(response, "usage", None)
        if raw is None:
            return None
        return TokenUsage(
            prompt_tokens=getattr(raw, "input_tokens", None),
            completion_tokens=getattr(raw, "output_tokens", None),
        )
