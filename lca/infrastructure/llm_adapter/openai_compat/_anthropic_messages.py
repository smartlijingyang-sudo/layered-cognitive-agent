"""Anthropic Messages API Strategy（DashScope Coding Plan /apps/anthropic）。

流事件对齐 Chat Completions：``REASONING_TEXT_DELTA`` / ``OUTPUT_TEXT_DELTA`` /
``FUNCTION_CALL_ARGUMENTS_DELTA`` / ``COMPLETED``。思考不进 ``response.text``。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent, TokenUsage
from lca.contracts.protocols import Tool
from lca.infrastructure.llm_adapter.openai_compat._anthropic_stream import (
    _AnthropicStreamDecoder,
    _feed_sse_line,
)
from lca.infrastructure.llm_adapter.openai_compat._history import (
    anthropic_messages_with_history,
)
from lca.infrastructure.llm_adapter.openai_compat._shared import (
    _RawToolCall,
    build_llm_response,
    build_request_generation,
    strip_observability_kwargs,
)
from lca.infrastructure.llm_adapter.settings import DEFAULT_MAX_TOKENS

_ANTHROPIC_VERSION = "2023-06-01"
_ANTHROPIC_URL_MARKERS = ("/apps/anthropic",)
_HTTP_TIMEOUT = httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0)
_DASHSCOPE_EXTRAS = (
    "enable_thinking",
    "enable_search",
    "top_k",
    "search_options",
    "repetition_penalty",
)


def looks_like_anthropic_base_url(base_url: str | None) -> bool:
    """DashScope Coding Plan 等 Anthropic 兼容口，不能拼 /chat/completions。"""
    if not base_url:
        return False
    lowered = base_url.rstrip("/").lower()
    return any(marker in lowered for marker in _ANTHROPIC_URL_MARKERS)


def anthropic_messages_url(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        return f"{root}/messages"
    return f"{root}/v1/messages"


def to_anthropic_tool_spec(tool: Tool) -> dict[str, Any]:
    schema = tool.parameters if isinstance(tool.parameters, dict) else {"type": "object"}
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": schema,
    }


class _AnthropicMessagesStrategy:
    def __init__(self, *, api_key: str, base_url: str, default_model: str) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._model = default_model

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        payload, headers = self._build_request(prompt, stream=False, **kwargs)
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.post(
                anthropic_messages_url(self._base_url),
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            body = response.json()
        return self._to_llm_response(body)

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        payload, headers = self._build_request(prompt, stream=True, **kwargs)
        decoder = _AnthropicStreamDecoder(default_model=str(payload.get("model") or self._model))
        data_lines: list[str] = []
        async with (
            httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client,
            client.stream(
                "POST",
                anthropic_messages_url(self._base_url),
                json=payload,
                headers=headers,
            ) as response,
        ):
            response.raise_for_status()
            async for line in response.aiter_lines():
                for event_payload in _feed_sse_line(data_lines, line):
                    for event in decoder.push(event_payload):
                        yield event
        for event in decoder.finish():
            yield event

    def _build_request(
        self, prompt: str, *, stream: bool, **kwargs: Any
    ) -> tuple[dict[str, Any], dict[str, str]]:
        cleaned = strip_observability_kwargs(kwargs)
        tools = cleaned.pop("tools", None)
        history = cleaned.pop("history", None) or []
        model = str(cleaned.pop("model", self._model))
        generation = build_request_generation(
            model=model,
            has_tools=bool(tools),
            kwargs=cleaned,
        )
        extra = generation.pop("extra_body", None) or {}
        max_tokens = int(generation.pop("max_tokens", DEFAULT_MAX_TOKENS) or DEFAULT_MAX_TOKENS)
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": anthropic_messages_with_history(prompt, history)
            if history
            else [{"role": "user", "content": prompt}],
        }
        if stream:
            payload["stream"] = True
        temperature = generation.pop("temperature", None)
        if temperature is not None:
            payload["temperature"] = temperature
        top_p = generation.pop("top_p", None)
        if top_p is not None:
            payload["top_p"] = top_p
        if isinstance(extra, dict):
            for key in _DASHSCOPE_EXTRAS:
                if key in extra:
                    payload[key] = extra[key]
        if tools:
            payload["tools"] = [to_anthropic_tool_spec(t) for t in tools]
        headers = {
            "content-type": "application/json",
            "x-api-key": self._api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "authorization": f"Bearer {self._api_key}",
        }
        return payload, headers

    def _to_llm_response(self, body: dict[str, Any]) -> LLMResponse:
        text_parts: list[str] = []
        raw_tools: list[_RawToolCall] = []
        for block in body.get("content") or []:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "text":
                piece = block.get("text")
                if isinstance(piece, str) and piece:
                    text_parts.append(piece)
            elif block_type == "tool_use":
                raw_input = block.get("input")
                if isinstance(raw_input, str):
                    arguments_json = raw_input
                else:
                    arguments_json = json.dumps(raw_input or {}, ensure_ascii=False)
                raw_tools.append(
                    _RawToolCall(
                        name=str(block.get("name") or ""),
                        arguments_json=arguments_json,
                        call_id=str(block.get("id") or ""),
                    )
                )
        usage_raw = body.get("usage")
        usage_dict = usage_raw if isinstance(usage_raw, dict) else {}
        usage = TokenUsage(
            prompt_tokens=usage_dict.get("input_tokens"),
            completion_tokens=usage_dict.get("output_tokens"),
        )
        return build_llm_response(
            text="".join(text_parts),
            tool_calls=raw_tools or None,
            model=str(body.get("model") or self._model),
            usage=usage,
            finish_reason=body.get("stop_reason"),
        )
