"""OpenAI-compatible HTTP surface.

- Non-agent (title / embeddings / responses): upstream OpenAI-shaped APIs.
- Agent runs: migrated to POST /v1/agent/runs + GET .../timeline (ADR-0053 Phase 3b).
"""

from __future__ import annotations

import json
from typing import Any

from openai import APIError
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from gateway._http import cors_headers
from gateway.lobehub_bridge.request_classifier import classify_lobehub_chat_request
from gateway.mode_catalog import DEFAULT_MODE, MODE_DEFINITIONS
from gateway.model_registry import get_model_registry
from gateway.openai_structured_llm import (
    StructuredLLMError,
    build_responses_payload,
    create_embeddings,
    create_simple_completion,
    create_structured_completion,
    extract_json_schema_format,
    normalize_responses_input,
    resolve_upstream_model,
)
from gateway.run_executor import llm_status
from lca.contracts.atoms.ids import new_id

_OPENAI_CHAT_ID_PREFIX = "chatcmpl-"


def _lca_models_payload() -> dict[str, Any]:
    registry = get_model_registry()
    data: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in [DEFAULT_MODE, *MODE_DEFINITIONS.keys()]:
        if key not in seen:
            data.append({"id": key, "object": "model", "created": 0, "owned_by": "lca"})
            seen.add(key)
    for model_def in registry.list_available():
        if model_def.id not in seen:
            data.append(
                {
                    "id": model_def.id,
                    "object": "model",
                    "created": 0,
                    "owned_by": model_def.provider,
                }
            )
            seen.add(model_def.id)
    return {"object": "list", "data": data}


def _error_response(
    message: str,
    *,
    status_code: int,
    error_type: str = "invalid_request_error",
    code: str | None = None,
) -> JSONResponse:
    err: dict[str, Any] = {"message": message, "type": error_type}
    if code:
        err["code"] = code
    return JSONResponse({"error": err}, status_code=status_code, headers=cors_headers())


async def list_models(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    return JSONResponse(_lca_models_payload(), headers=cors_headers())


async def _passthrough_chat_completion(
    *,
    messages: list[Any],
    model: str,
    stream: bool,
    chat_id: str,
) -> JSONResponse | StreamingResponse:
    """Title / mini helper — real upstream OpenAI-shaped completion."""
    try:
        text, usage = await create_simple_completion(messages=messages, model=model)
    except StructuredLLMError as exc:
        return _error_response(str(exc), status_code=502, error_type="server_error")
    except APIError as exc:
        return _error_response(str(exc), status_code=502, error_type="server_error")

    if stream:

        async def _body() -> Any:
            chunk = {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": text}}],
            }
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode()
            stop = {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            yield f"data: {json.dumps(stop, ensure_ascii=False)}\n\n".encode()
            yield b"data: [DONE]\n\n"

        return StreamingResponse(
            _body(),
            media_type="text/event-stream",
            headers=cors_headers(**{"Cache-Control": "no-cache"}),
        )

    body = {
        "id": chat_id,
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": usage or {},
    }
    return JSONResponse(body, headers=cors_headers())


async def _chat_completions_from_body(body: dict[str, Any]) -> JSONResponse | StreamingResponse:
    model = str(body.get("model", DEFAULT_MODE))
    stream = bool(body.get("stream", False))
    messages = body.get("messages") or []
    if not isinstance(messages, list):
        return _error_response("messages must be an array", status_code=400)

    chat_id = f"{_OPENAI_CHAT_ID_PREFIX}{new_id('chat')}"

    # Structured output (generateObject) — standard OpenAI response_format
    if body.get("response_format") is not None:
        return await _structured_chat_completion(body, model, messages, chat_id)

    # Title generation — bypass LCA agent runs
    if classify_lobehub_chat_request(messages) == "title":
        return await _passthrough_chat_completion(
            messages=messages, model=model, stream=stream, chat_id=chat_id
        )

    return _error_response(
        "Agent runs must use POST /v1/agent/runs + GET /v1/agent/runs/{id}/timeline. "
        "/v1/chat/completions is reserved for title generation and structured output only.",
        status_code=400,
        code="agent_runs_migrated",
    )


async def _structured_chat_completion(
    body: dict[str, Any], model: str, messages: list[Any], chat_id: str
) -> JSONResponse:
    """Handle chat completions with response_format (generateObject)."""
    # Filter out unsupported roles (developer) for upstream APIs
    supported_roles = {"system", "user", "assistant", "tool", "function"}
    filtered_messages = [
        m for m in messages if isinstance(m, dict) and m.get("role") in supported_roles
    ]

    # Extract json_schema from either Responses-style or chat-style format
    json_schema = extract_json_schema_format(body) or body.get("response_format")
    if not isinstance(json_schema, dict) or json_schema.get("type") != "json_schema":
        # Fallback to simple completion for non-JSON-schema formats
        try:
            text, usage = await create_simple_completion(messages=filtered_messages, model=model)
        except (StructuredLLMError, APIError) as exc:
            return _error_response(str(exc), status_code=502, error_type="server_error")
    else:
        try:
            text, usage = await create_structured_completion(
                messages=filtered_messages, model=model, response_format=json_schema
            )
        except (StructuredLLMError, APIError) as exc:
            return _error_response(str(exc), status_code=502, error_type="server_error")

    return JSONResponse(_chat_response(chat_id, text, usage), headers=cors_headers())


def _chat_response(chat_id: str, content: str, usage: dict | None) -> dict[str, Any]:
    return {
        "id": chat_id,
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": usage or {},
    }


async def chat_completions(request: Request) -> JSONResponse | StreamingResponse:
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return _error_response("invalid JSON body", status_code=400)
    if not isinstance(body, dict):
        return _error_response("request body must be a JSON object", status_code=400)
    if not llm_status()["llm_available"]:
        return _error_response(
            "LLM_API_KEY 未配置，无法执行 LCA run。",
            status_code=503,
            error_type="service_unavailable",
            code="lca_llm_unavailable",
        )
    return await _chat_completions_from_body(body)


async def embeddings_create(request: Request) -> JSONResponse:
    """OpenAI-compatible embeddings — proxy to upstream LLM via LCA gateway."""
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return _error_response("invalid JSON body", status_code=400)

    if not isinstance(body, dict):
        return _error_response("request body must be a JSON object", status_code=400)

    if not llm_status()["llm_available"]:
        return _error_response(
            "LLM_API_KEY 未配置，无法执行 embeddings。",
            status_code=503,
            error_type="service_unavailable",
            code="lca_llm_unavailable",
        )

    raw_input = body.get("input")
    if raw_input is None:
        return _error_response("input is required", status_code=400)

    model = str(body.get("model", "text-embedding-3-small"))
    try:
        payload = await create_embeddings(
            model=model,
            raw_input=raw_input,
            dimensions=body.get("dimensions"),
            encoding_format=body.get("encoding_format"),
        )
    except (StructuredLLMError, APIError) as exc:
        return _error_response(
            str(exc),
            status_code=502,
            error_type="server_error",
            code="lca_embeddings_failed",
        )
    return JSONResponse(payload, headers=cors_headers())


async def responses_create(request: Request) -> JSONResponse | StreamingResponse:
    """OpenAI Responses API shim for LobeHub AgentSignal ``generateObject``."""
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return _error_response("invalid JSON body", status_code=400)

    if not isinstance(body, dict):
        return _error_response("request body must be a JSON object", status_code=400)

    if not llm_status()["llm_available"]:
        return _error_response(
            "LLM_API_KEY 未配置，无法执行 structured output。",
            status_code=503,
            error_type="service_unavailable",
            code="lca_llm_unavailable",
        )

    model = str(body.get("model", DEFAULT_MODE))
    messages = normalize_responses_input(body.get("input"))
    if not messages:
        return _error_response("input must include at least one message", status_code=400)

    response_format = extract_json_schema_format(body)
    if response_format is None:
        chat_body = {
            "model": model,
            "stream": bool(body.get("stream", False)),
            "messages": messages,
        }
        return await _chat_completions_from_body(chat_body)

    try:
        output_text, usage = await create_structured_completion(
            messages=messages,
            model=model,
            response_format=response_format,
        )
    except (StructuredLLMError, APIError) as exc:
        return _error_response(
            str(exc),
            status_code=502,
            error_type="server_error",
            code="lca_structured_llm_failed",
        )

    upstream_model = resolve_upstream_model(model)
    payload = build_responses_payload(
        model=upstream_model,
        output_text=output_text,
        usage=usage,
    )
    return JSONResponse(payload, headers=cors_headers())
