"""Anthropic Messages API Strategy（DashScope Coding Plan /apps/anthropic）。

流事件对齐 Chat Completions：``REASONING_TEXT_DELTA`` / ``OUTPUT_TEXT_DELTA`` /
``FUNCTION_CALL_ARGUMENTS_DELTA`` / ``COMPLETED``。思考不进 ``response.text``。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent, TokenUsage
from lca.contracts.protocols import Tool
from lca.layer0_infra.llm_adapter.openai_compat._shared import (
    ThinkTagStreamSplitter,
    _RawToolCall,
    build_llm_response,
    build_request_generation,
    strip_observability_kwargs,
)
from lca.layer0_infra.llm_adapter.settings import DEFAULT_MAX_TOKENS

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


class _AnthropicStreamDecoder:
    """Anthropic SSE JSON → Chat Completions 同构的 ``LLMStreamEvent``。"""

    def __init__(self, *, default_model: str) -> None:
        self._model = default_model
        self._text_parts: list[str] = []
        self._tools: dict[int, dict[str, str]] = {}
        self._splitter = ThinkTagStreamSplitter()
        self._usage: TokenUsage | None = None
        self._stop_reason: str | None = None
        self._done = False

    def push(self, payload: dict[str, Any]) -> list[LLMStreamEvent]:
        event_type = str(payload.get("type") or "")
        if event_type == "message_start":
            self._on_message_start(payload)
            return []
        if event_type == "content_block_start":
            return self._on_block_start(payload)
        if event_type == "content_block_delta":
            return self._on_block_delta(payload)
        if event_type == "message_delta":
            self._on_message_delta(payload)
            return []
        if event_type == "message_stop":
            return self.finish()
        return []

    def finish(self) -> list[LLMStreamEvent]:
        if self._done:
            return []
        self._done = True
        out: list[LLMStreamEvent] = []
        for kind, piece in self._splitter.flush():
            out.extend(self._emit_split(kind, piece))
        out.append(
            LLMStreamEvent(
                type=LLMStreamEventType.COMPLETED,
                response=build_llm_response(
                    text="".join(self._text_parts),
                    tool_calls=self._raw_tools() or None,
                    model=self._model,
                    usage=self._usage,
                    finish_reason=self._stop_reason,
                ),
            )
        )
        return out

    def _on_message_start(self, payload: dict[str, Any]) -> None:
        message = payload.get("message")
        if not isinstance(message, dict):
            return
        model = message.get("model")
        if isinstance(model, str) and model:
            self._model = model
        self._merge_usage(message.get("usage"))

    def _on_message_delta(self, payload: dict[str, Any]) -> None:
        delta = payload.get("delta")
        if isinstance(delta, dict):
            stop = delta.get("stop_reason")
            if stop:
                self._stop_reason = str(stop)
        self._merge_usage(payload.get("usage"))

    def _on_block_start(self, payload: dict[str, Any]) -> list[LLMStreamEvent]:
        index = int(payload.get("index") or 0)
        block = payload.get("content_block")
        if not isinstance(block, dict):
            return []
        block_type = block.get("type")
        if block_type == "thinking":
            piece = _first_str(block, "thinking", "text")
            if piece:
                return [
                    LLMStreamEvent(type=LLMStreamEventType.REASONING_TEXT_DELTA, text=piece),
                ]
            return []
        if block_type == "text":
            piece = _first_str(block, "text")
            return self._feed_text(piece) if piece else []
        if block_type == "tool_use":
            entry = {
                "id": str(block.get("id") or ""),
                "name": str(block.get("name") or ""),
                "arguments": "",
            }
            raw_input = block.get("input")
            if isinstance(raw_input, dict) and raw_input:
                entry["arguments"] = json.dumps(raw_input, ensure_ascii=False)
            elif isinstance(raw_input, str) and raw_input:
                entry["arguments"] = raw_input
            self._tools[index] = entry
            return [
                LLMStreamEvent(
                    type=LLMStreamEventType.FUNCTION_CALL_ARGUMENTS_DELTA,
                    tool_call_id=entry["id"] or None,
                    tool_name=entry["name"] or None,
                    arguments_delta="",
                )
            ]
        return []

    def _on_block_delta(self, payload: dict[str, Any]) -> list[LLMStreamEvent]:
        index = int(payload.get("index") or 0)
        delta = payload.get("delta")
        if not isinstance(delta, dict):
            return []
        delta_type = delta.get("type")
        if delta_type == "thinking_delta":
            piece = _first_str(delta, "thinking", "text")
            if piece:
                return [
                    LLMStreamEvent(type=LLMStreamEventType.REASONING_TEXT_DELTA, text=piece),
                ]
            return []
        if delta_type == "text_delta":
            piece = _first_str(delta, "text")
            return self._feed_text(piece) if piece else []
        if delta_type == "input_json_delta":
            piece = _first_str(delta, "partial_json")
            entry = self._tools.setdefault(index, {"id": "", "name": "", "arguments": ""})
            if piece:
                entry["arguments"] += piece
            return [
                LLMStreamEvent(
                    type=LLMStreamEventType.FUNCTION_CALL_ARGUMENTS_DELTA,
                    tool_call_id=entry["id"] or None,
                    tool_name=None,
                    arguments_delta=piece,
                )
            ]
        return []

    def _feed_text(self, chunk: str) -> list[LLMStreamEvent]:
        out: list[LLMStreamEvent] = []
        for kind, piece in self._splitter.feed(chunk):
            out.extend(self._emit_split(kind, piece))
        return out

    def _emit_split(self, kind: str, piece: str) -> list[LLMStreamEvent]:
        if not piece:
            return []
        if kind == "reasoning":
            return [LLMStreamEvent(type=LLMStreamEventType.REASONING_TEXT_DELTA, text=piece)]
        self._text_parts.append(piece)
        return [LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text=piece)]

    def _merge_usage(self, raw: Any) -> None:
        if not isinstance(raw, dict):
            return
        prev_in = self._usage.prompt_tokens if self._usage is not None else None
        prev_out = self._usage.completion_tokens if self._usage is not None else None
        prompt = raw.get("input_tokens", prev_in)
        completion = raw.get("output_tokens", prev_out)
        self._usage = TokenUsage(prompt_tokens=prompt, completion_tokens=completion)

    def _raw_tools(self) -> list[_RawToolCall]:
        result: list[_RawToolCall] = []
        for index in sorted(self._tools):
            entry = self._tools[index]
            if not entry.get("name"):
                continue
            result.append(
                _RawToolCall(
                    name=entry["name"],
                    arguments_json=entry.get("arguments", ""),
                    call_id=entry.get("id", ""),
                )
            )
        return result


def _first_str(obj: dict[str, Any], *names: str) -> str:
    for name in names:
        value = obj.get(name)
        if isinstance(value, str) and value:
            return value
    return ""


def _feed_sse_line(data_lines: list[str], raw: str) -> list[dict[str, Any]]:
    line = raw.rstrip("\r")
    if line == "":
        if not data_lines:
            return []
        data = "\n".join(data_lines)
        data_lines.clear()
        if not data.strip() or data.strip() == "[DONE]":
            return []
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            return []
        return [parsed] if isinstance(parsed, dict) else []
    if line.startswith(":"):
        return []
    if line.startswith("data:"):
        data_lines.append(line[5:].lstrip())
    return []


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
            "messages": [{"role": "user", "content": prompt}],
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
