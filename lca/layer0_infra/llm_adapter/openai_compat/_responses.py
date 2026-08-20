"""Responses API Strategy —— 默认 wire protocol。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent, TokenUsage
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.protocols import Tool
from lca.layer0_infra.llm_adapter.openai_compat._history import openai_messages_with_history
from lca.layer0_infra.llm_adapter.openai_compat._shared import (
    _RawToolCall,
    build_llm_response,
    build_request_generation,
)

_RESPONSE_OUTPUT_TEXT_DELTA = "response.output_text.delta"
_RESPONSE_REASONING_TEXT_DELTA = "response.reasoning_text.delta"
_RESPONSE_REASONING_SUMMARY_DELTA = "response.reasoning_summary_text.delta"
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
            elif event_type in (
                _RESPONSE_REASONING_TEXT_DELTA,
                _RESPONSE_REASONING_SUMMARY_DELTA,
            ):
                delta_text = getattr(event, "delta", None) or ""
                if delta_text:
                    yield LLMStreamEvent(
                        type=LLMStreamEventType.REASONING_TEXT_DELTA,
                        text=delta_text,
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
        history = kwargs.pop("history", None) or []
        model = kwargs.pop("model", self._model)
        generation = build_request_generation(
            model=model,
            has_tools=bool(tools),
            kwargs=kwargs,
        )
        # Responses API 用 max_output_tokens；其余生成参数保持一致
        max_tokens = generation.pop("max_tokens", None)
        api_kwargs: dict[str, Any] = {
            "model": model,
            "input": openai_messages_with_history(prompt, history) if history else prompt,
            **generation,
        }
        if max_tokens is not None:
            api_kwargs["max_output_tokens"] = max_tokens
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
            finish_reason=self._extract_finish_reason(response),
        )

    @staticmethod
    def _extract_finish_reason(response: Any) -> str | None:
        """Responses API: status + incomplete_details.reason → finish_reason 信号。"""
        status = getattr(response, "status", None)
        if status is None:
            return None
        status_s = str(status).strip().lower()
        if status_s == "incomplete":
            details = getattr(response, "incomplete_details", None)
            reason = getattr(details, "reason", None) if details is not None else None
            if reason:
                return str(reason)
            return "length"
        if status_s in ("failed", "cancelled"):
            return "error"
        if status_s == TaskStatus.COMPLETED:
            # 有 function_call 时对齐 Chat 的 tool_calls 语义
            for item in getattr(response, "output", []) or []:
                if getattr(item, "type", None) == "function_call":
                    return "tool_calls"
            return "stop"
        return status_s

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
