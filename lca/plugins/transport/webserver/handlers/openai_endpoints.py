"""HTTP endpoint adapters for the Gateway OpenAI-compatible housekeeper API.

Three live routes:``/v1/models``, ``/v1/chat/completions``,
``/v1/embeddings``, ``/v1/responses``. The POST routes depend on the
``llm_resolver`` capability (declared via :class:`RouteSpec.requires` in
``routes_openai_compat_files``); boot fails fast if the resolver is
absent, so each handler is now a thin glue over ``chat_completions_from_body``
and friends.
"""

from __future__ import annotations

import json
from typing import Any

from openai import APIError
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from lca.cognition.team.modes_catalog import DEFAULT_MODE
from lca.infrastructure.openai_compat import (
    StructuredLLMError,
    build_responses_payload,
    create_embeddings,
    create_structured_completion,
    extract_json_schema_format,
    normalize_responses_input,
    resolve_upstream_model,
)
from lca.plugins.transport.webserver.handlers.cors import cors_headers
from lca.plugins.transport.webserver.handlers.openai_housekeeping import (
    chat_completions_from_body,
    passthrough_responses_completion,
)
from lca.plugins.transport.webserver.handlers.openai_protocol import (
    error_response,
    lca_models_payload,
)


async def list_models(request: Request) -> JSONResponse:
    """Serve the static LCA UI model catalog with preflight support."""
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    return JSONResponse(lca_models_payload(), headers=cors_headers())


async def chat_completions(request: Request) -> JSONResponse | StreamingResponse:
    """``POST /v1/chat/completions`` — housekeeper chat completion proxy.

    Boot-period readiness is enforced by the routes plugin; reaching this
    handler means the LLM resolver is bound. Mode catalog ids still go
    through :func:`chat_completions_from_body`.
    """
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await _decode_json_object(request)
    if isinstance(body, JSONResponse):
        return body
    return await chat_completions_from_body(body)


async def embeddings_create(request: Request) -> JSONResponse:
    """``POST /v1/embeddings`` — proxy embeddings through the bound LLM."""
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await _decode_json_object(request)
    if isinstance(body, JSONResponse):
        return body
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
    """``POST /v1/responses`` — housekeeper Responses API through OpenAI semantics."""
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await _decode_json_object(request)
    if isinstance(body, JSONResponse):
        return body
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


async def _decode_json_object(request: Request) -> dict[str, Any] | JSONResponse:
    """Decode a JSON object body, returning a wire-valid 400 envelope on failure."""
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return error_response("invalid JSON body", status_code=400)
    if not isinstance(body, dict):
        return error_response("request body must be a JSON object", status_code=400)
    return body


__all__ = ["chat_completions", "embeddings_create", "list_models", "responses_create"]
