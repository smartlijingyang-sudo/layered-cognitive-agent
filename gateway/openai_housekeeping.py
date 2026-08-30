"""Completion service for LobeHub housekeeper and structured-output calls."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from openai import APIError
from starlette.responses import JSONResponse, StreamingResponse

from gateway.modes import DEFAULT_MODE
from gateway.openai_protocol import (
    chat_response,
    error_response,
    new_chat_id,
    streaming_chat_response,
)
from lca.layer0_infra.openai_compat import (
    StructuredLLMError,
    build_responses_payload,
    create_simple_completion,
    create_structured_completion,
    extract_json_schema_format,
    resolve_upstream_model,
)


async def chat_completions_from_body(body: dict[str, Any]) -> JSONResponse | StreamingResponse:
    """Handle a validated Chat Completions request body without HTTP concerns."""
    model = str(body.get("model", DEFAULT_MODE))
    stream = bool(body.get("stream", False))
    messages = body.get("messages") or []
    if not isinstance(messages, list):
        return error_response("messages must be an array", status_code=400)
    chat_id = new_chat_id()
    if body.get("response_format") is not None:
        return await structured_chat_completion(body, model, messages, chat_id)
    return await passthrough_chat_completion(
        messages=messages,
        model=model,
        stream=stream,
        chat_id=chat_id,
    )


async def passthrough_chat_completion(
    *,
    messages: list[Any],
    model: str,
    stream: bool,
    chat_id: str,
) -> JSONResponse | StreamingResponse:
    """Run a title or mini-helper completion and encode its Chat Completion response."""
    try:
        text, usage = await create_simple_completion(messages=messages, model=model)
    except (StructuredLLMError, APIError) as exc:
        return error_response(str(exc), status_code=502, error_type="server_error")
    if stream:
        return streaming_chat_response(chat_id, text)
    return JSONResponse(chat_response(chat_id, text, usage), headers=_cors_headers())


async def structured_chat_completion(
    body: dict[str, Any],
    model: str,
    messages: list[Any],
    chat_id: str,
) -> JSONResponse:
    """Run OpenAI `response_format` handling for LobeHub generateObject calls."""
    response_format = extract_json_schema_format(body) or body.get("response_format")
    try:
        if not isinstance(response_format, dict) or response_format.get("type") != "json_schema":
            text, usage = await create_simple_completion(messages=messages, model=model)
        else:
            text, usage = await create_structured_completion(
                messages=messages,
                model=model,
                response_format=response_format,
            )
    except (StructuredLLMError, APIError) as exc:
        return error_response(str(exc), status_code=502, error_type="server_error")
    return JSONResponse(chat_response(chat_id, text, usage), headers=_cors_headers())


def _cors_headers(**extra: str) -> dict[str, str]:
    """Import CORS construction lazily to keep protocol encoding dependency-focused."""
    from gateway.cors import cors_headers

    return cors_headers(**extra)


async def passthrough_responses_completion(
    *,
    messages: list[Any],
    model: str,
    stream: bool,
) -> JSONResponse | StreamingResponse:
    """Run a LobeHub-side housekeeper call and encode it as OpenAI Responses API.

    LobeHub's `handleResponseAPIMode` parses ``object: "response"`` envelopes and
    ``response.output_text.delta`` / ``response.completed`` SSE events; the upstream
    is still a plain Chat Completions model, so this adapts the wire shape to
    LobeHub without leaking provider-specific model ids or hardcoded virtual names.
    """
    try:
        text, usage = await create_simple_completion(messages=messages, model=model)
    except (StructuredLLMError, APIError) as exc:
        return error_response(str(exc), status_code=502, error_type="server_error")
    upstream_model = resolve_upstream_model(model)
    if stream:
        return streaming_responses_response(upstream_model, text, usage)
    return JSONResponse(
        build_responses_payload(model=upstream_model, output_text=text, usage=usage),
        headers=_cors_headers(),
    )


def streaming_responses_response(
    upstream_model: str, content: str, usage: dict[str, Any] | None
) -> StreamingResponse:
    """Adapt one complete Chat-Completions text reply into Responses-API SSE.

    Emits the minimum event set LobeHub's Responses stream parser needs:
    ``response.created`` → ``response.output_text.delta`` → ``response.completed``,
    followed by ``data: [DONE]`` so the openai SDK returns cleanly.
    """

    def _event(event_type: str, payload: dict[str, Any]) -> bytes:
        return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()

    async def body() -> AsyncIterator[bytes]:
        base = build_responses_payload(model=upstream_model, output_text=content, usage=usage)
        created = {
            "type": "response.created",
            "sequence_number": 0,
            "response": {**base, "output": [], "output_text": ""},
        }
        delta = {
            "type": "response.output_text.delta",
            "sequence_number": 1,
            "item_id": base["output"][0]["id"],
            "output_index": 0,
            "content_index": 0,
            "delta": content,
            "logprobs": [],
        }
        completed = {
            "type": "response.completed",
            "sequence_number": 2,
            "response": base,
        }
        for chunk in (
            _event("response.created", created),
            _event("response.output_text.delta", delta),
            _event("response.completed", completed),
        ):
            yield chunk
        yield b"data: [DONE]\n\n"

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers=_cors_headers(**{"Cache-Control": "no-cache"}),
    )


__all__ = [
    "chat_completions_from_body",
    "passthrough_chat_completion",
    "passthrough_responses_completion",
    "streaming_responses_response",
    "structured_chat_completion",
]
