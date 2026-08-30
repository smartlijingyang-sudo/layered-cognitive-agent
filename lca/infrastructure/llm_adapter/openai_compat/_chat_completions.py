"""Chat Completions API Strategy。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent, TokenUsage
from lca.contracts.protocols import Tool
from lca.infrastructure.llm_adapter.openai_compat._history import openai_messages_with_history
from lca.infrastructure.llm_adapter.openai_compat._shared import (
    ThinkTagStreamSplitter,
    _RawToolCall,
    build_llm_response,
    build_request_generation,
    extract_reasoning_text,
    pick_all_tool_calls,
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
        choice = response.choices[0]
        msg = choice.message
        usage = self._extract_usage(response)
        model = getattr(response, "model", "") or self._model
        finish_reason = getattr(choice, "finish_reason", None)
        text = msg.content or ""
        raw_tool_calls: list[_RawToolCall] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                raw_tool_calls.append(
                    _RawToolCall(
                        name=tc.function.name,
                        arguments_json=tc.function.arguments,
                        call_id=tc.id or "",
                    )
                )
        return build_llm_response(
            text=text,
            tool_calls=raw_tool_calls or None,
            model=model,
            usage=usage,
            finish_reason=finish_reason,
        )

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        api_kwargs = self._build_request_kwargs(prompt, **kwargs)
        api_kwargs["stream"] = True
        api_kwargs["stream_options"] = {"include_usage": True}

        accumulated_text = ""
        reasoning_text = ""
        tool_calls: dict[int, dict[str, str]] = {}
        think_splitter = ThinkTagStreamSplitter()
        finish_reason: str | None = None
        completed = False

        stream = await self._client.chat.completions.create(**api_kwargs)
        async for chunk in stream:
            if not chunk.choices:
                for kind, piece in think_splitter.flush():
                    if kind == "reasoning":
                        reasoning_text += piece
                        yield LLMStreamEvent(
                            type=LLMStreamEventType.REASONING_TEXT_DELTA,
                            text=piece,
                        )
                    elif piece:
                        accumulated_text += piece
                        yield LLMStreamEvent(
                            type=LLMStreamEventType.OUTPUT_TEXT_DELTA,
                            text=piece,
                        )
                usage = self._extract_usage(chunk)
                model = getattr(chunk, "model", "") or self._model
                yield LLMStreamEvent(
                    type=LLMStreamEventType.COMPLETED,
                    response=build_llm_response(
                        text=accumulated_text,
                        tool_calls=pick_all_tool_calls(tool_calls) or None,
                        model=model,
                        usage=usage,
                        finish_reason=finish_reason,
                    ),
                )
                completed = True
                return

            choice = chunk.choices[0]
            fr = getattr(choice, "finish_reason", None)
            if fr:
                finish_reason = fr
            delta = choice.delta
            reasoning_piece = extract_reasoning_text(delta)
            if reasoning_piece:
                reasoning_text += reasoning_piece
                yield LLMStreamEvent(
                    type=LLMStreamEventType.REASONING_TEXT_DELTA,
                    text=reasoning_piece,
                )

            if delta.content:
                for kind, piece in think_splitter.feed(delta.content):
                    if kind == "reasoning":
                        reasoning_text += piece
                        yield LLMStreamEvent(
                            type=LLMStreamEventType.REASONING_TEXT_DELTA,
                            text=piece,
                        )
                    elif piece:
                        accumulated_text += piece
                        yield LLMStreamEvent(
                            type=LLMStreamEventType.OUTPUT_TEXT_DELTA,
                            text=piece,
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

        if completed:
            return
        for kind, piece in think_splitter.flush():
            if kind == "reasoning":
                reasoning_text += piece
                yield LLMStreamEvent(
                    type=LLMStreamEventType.REASONING_TEXT_DELTA,
                    text=piece,
                )
            elif piece:
                accumulated_text += piece
                yield LLMStreamEvent(
                    type=LLMStreamEventType.OUTPUT_TEXT_DELTA,
                    text=piece,
                )
        yield LLMStreamEvent(
            type=LLMStreamEventType.COMPLETED,
            response=build_llm_response(
                text=accumulated_text,
                tool_calls=pick_all_tool_calls(tool_calls) or None,
                model=self._model,
                usage=None,
                finish_reason=finish_reason,
            ),
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
        api_kwargs: dict[str, Any] = {
            "model": model,
            "messages": openai_messages_with_history(prompt, history)
            if history
            else [{"role": "user", "content": prompt}],
            **generation,
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
