"""OpenAI-compatible HTTP surface + agent timeline stream.

- Non-agent (title / embeddings / responses): upstream OpenAI-shaped APIs.
- Agent (solo/team): **timeline.v1 SSE only** — no chat.completion.chunk, no lca.events.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from openai import APIError
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from gateway._http import cors_headers
from gateway.lobehub_bridge import prepare_run_from_messages
from gateway.lobehub_bridge.request_classifier import classify_lobehub_chat_request
from gateway.mode_catalog import DEFAULT_MODE, MODE_DEFINITIONS, resolve_lca_mode
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
from gateway.run_executor import create_run_session, llm_status, schedule_run
from gateway.timeline.stream import stream_timeline_sse
from lca.contracts.atoms.ids import new_id

_OPENAI_CHAT_ID_PREFIX = "chatcmpl-"
_log = structlog.get_logger(__name__)


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
    """Title / mini helpers — real upstream OpenAI-shaped completion."""
    try:
        text, usage = await create_simple_completion(messages=messages, model=model)
    except StructuredLLMError as exc:
        return _error_response(str(exc), status_code=502, error_type="server_error")
    except APIError as exc:
        return _error_response(str(exc), status_code=502, error_type="server_error")

    if stream:

        async def _body() -> Any:
            # Minimal OpenAI stream for non-agent only
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
    if classify_lobehub_chat_request(messages) == "title":
        return await _passthrough_chat_completion(
            messages=messages,
            model=model,
            stream=stream,
            chat_id=chat_id,
        )

    from gateway.app import get_file_store, get_registry

    run_input = await prepare_run_from_messages(messages, get_file_store())
    if not run_input.user_text.strip():
        return _error_response("messages must include a non-empty user message", status_code=400)

    mode = resolve_lca_mode(model)
    registry = get_registry()
    session = registry.find_inflight_run(
        user_text=run_input.user_text,
        mode=mode,
        attachment_ids=run_input.attachment_ids,
    )
    if session is None:
        session = create_run_session(
            registry,
            question=run_input.question,
            user_text=run_input.user_text,
            mode=mode,
            attachment_ids=run_input.attachment_ids,
            prior_turns=run_input.prior_turns,
        )
        schedule_run(registry, session)
    else:
        _log.info(
            "openai_run_deduped",
            run_id=session.run_id,
            mode=mode,
            user_text_preview=run_input.user_text[:80],
        )

    # Agent path: timeline.v1 only (stream required for UI)
    if not stream:
        return _error_response(
            "LCA agent runs require stream=true (timeline.v1 SSE). "
            "Prefer POST /v1/agent/runs + GET .../timeline.",
            status_code=400,
            code="timeline_stream_required",
        )

    async def _body() -> Any:
        async for frame in stream_timeline_sse(session.bus.subscribe()):
            yield frame

    return StreamingResponse(
        _body(),
        media_type="text/event-stream",
        headers=cors_headers(
            **{
                "Cache-Control": "no-cache",
                "X-LCA-Stream": "timeline.v1",
                "X-LCA-Run-Id": session.run_id,
            }
        ),
    )


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
