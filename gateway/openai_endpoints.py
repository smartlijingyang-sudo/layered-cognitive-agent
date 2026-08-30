"""HTTP endpoint adapters for the Gateway OpenAI-compatible housekeeper API."""

from __future__ import annotations

import json
from typing import Any

from openai import APIError
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from gateway.cors import cors_headers
from gateway.modes import DEFAULT_MODE
from gateway.openai_housekeeping import (
    chat_completions_from_body,
    passthrough_responses_completion,
)
from gateway.openai_protocol import error_response, lca_models_payload
from gateway.runs.execute.execute import llm_status
from lca.infrastructure.openai_compat import (
    StructuredLLMError,
    build_responses_payload,
    create_embeddings,
    create_structured_completion,
    extract_json_schema_format,
    normalize_responses_input,
    resolve_upstream_model,
)


async def list_models(request: Request) -> JSONResponse:
    """Serve the static LCA UI model catalog with preflight support."""
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    return JSONResponse(lca_models_payload(), headers=cors_headers())


async def chat_completions(request: Request) -> JSONResponse | StreamingResponse:
    """Serve a housekeeper Chat Completion after validating boot and LLM availability.

    ADR-0100: this route never starts an Agent run. Mode catalog ids still
    ``resolve_upstream_model`` through ``chat_completions_from_body``.
    """
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await request_json_body(request)
    if isinstance(body, JSONResponse):
        return body
    ctx = getattr(request.app.state, "ctx", None)
    if ctx is None:
        return error_response(
            "gateway boot 未加载 profile，无法执行 LCA run。",
            status_code=503,
            error_type="service_unavailable",
            code="lca_plugin_ctx_missing",
        )
    if not llm_status(ctx)["llm_available"]:
        return llm_unavailable_response("LCA run")

    return await chat_completions_from_body(body)


async def embeddings_create(request: Request) -> JSONResponse:
    """Proxy an OpenAI-compatible embeddings request through the configured LLM."""
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await request_json_body(request)
    if isinstance(body, JSONResponse):
        return body
    if not llm_status(getattr(request.app.state, "ctx", None))["llm_available"]:
        return llm_unavailable_response("embeddings")
    raw_input = body.get("input")
    if raw_input is None:
        return error_response("input is required", status_code=400)
    model = str(body.get("model", "text-embedding-3-small"))
    try:
        payload = await create_embeddings(
            model=model,
            raw_input=raw_input,
            dimensions=body.get("dimensions"),
            encoding_format=body.get("encoding_format"),
        )
    except (StructuredLLMError, APIError) as exc:
        return error_response(
            str(exc),
            status_code=502,
            error_type="server_error",
            code="lca_embeddings_failed",
        )
    return JSONResponse(payload, headers=cors_headers())


async def responses_create(request: Request) -> JSONResponse | StreamingResponse:
    """Serve LobeHub AgentSignal structured output through OpenAI Responses semantics."""
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await request_json_body(request)
    if isinstance(body, JSONResponse):
        return body
    if not llm_status(getattr(request.app.state, "ctx", None))["llm_available"]:
        return llm_unavailable_response("structured output")
    model = str(body.get("model", DEFAULT_MODE))
    messages = normalize_responses_input(body.get("input"))
    if not messages:
        return error_response("input must include at least one message", status_code=400)
    response_format = extract_json_schema_format(body)
    if response_format is None:
        # No structured output requested (title summarization, mini-helper calls,
        # etc.). LobeHub's Responses parser still expects `object: "response"`
        # envelopes and `response.output_text.delta` SSE events — adapt the wire
        # shape here so LobeHub code stays untouched and future model swaps do
        # not need a new patch.
        return await passthrough_responses_completion(
            messages=messages,
            model=model,
            stream=bool(body.get("stream", False)),
        )
    try:
        output_text, usage = await create_structured_completion(
            messages=messages,
            model=model,
            response_format=response_format,
        )
    except (StructuredLLMError, APIError) as exc:
        return error_response(
            str(exc),
            status_code=502,
            error_type="server_error",
            code="lca_structured_llm_failed",
        )
    payload = build_responses_payload(
        model=resolve_upstream_model(model),
        output_text=output_text,
        usage=usage,
    )
    return JSONResponse(payload, headers=cors_headers())


async def request_json_body(request: Request) -> dict[str, Any] | JSONResponse:
    """Decode a JSON object, returning a wire-valid error for malformed request bodies."""
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return error_response("invalid JSON body", status_code=400)
    if not isinstance(body, dict):
        return error_response("request body must be a JSON object", status_code=400)
    return body


def llm_unavailable_response(operation: str) -> JSONResponse:
    """Return the stable service-unavailable response for missing LLM configuration."""
    return error_response(
        f"LLM_API_KEY 未配置，无法执行 {operation}。",
        status_code=503,
        error_type="service_unavailable",
        code="lca_llm_unavailable",
    )


__all__ = ["chat_completions", "embeddings_create", "list_models", "responses_create"]
