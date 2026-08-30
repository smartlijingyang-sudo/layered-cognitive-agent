"""HTTP command handlers for the run carrier.

The module owns request decoding and command-to-response translation. Ownership
of the run lifecycle remains behind the composition-selected ``RunPort``, so
the HTTP carrier never learns concrete runtime details.
"""

from __future__ import annotations

import json
from typing import Any, cast

from starlette.requests import Request
from starlette.responses import JSONResponse

from gateway.cors import cors_headers
from gateway.modes import resolve_profile_mode
from gateway.runs.execute.execute import llm_status
from gateway.runs.ingest.ingress import prepare_run_from_messages
from gateway.runs.observability.identity import parse_agent_ref
from gateway.runs.terminal.port import RunPort, RunRequest
from lca.contracts.mechanisms.capability import MissingCapabilityError
from lca.infrastructure.file_store import LocalFileStore


def _file_store_of(request: Request) -> LocalFileStore:
    return cast("LocalFileStore", request.app.state.file_store)


def _run_port_of(request: Request) -> RunPort:
    """Return the single run owner selected by the composition root."""
    return cast("RunPort", request.app.state.run_port)


def _ctx_of(request: Request) -> Any:
    """Cordis Context booted by create_app; absent when no profile was loaded."""
    return getattr(request.app.state, "ctx", None)


def _err(
    message: str,
    *,
    status_code: int,
    error_type: str = "invalid_request_error",
    code: str | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {"message": message, "type": error_type}
    if code:
        error["code"] = code
    return JSONResponse({"error": error}, status_code=status_code, headers=cors_headers())


async def create_run(request: Request) -> JSONResponse:
    """POST /runs — dispatch a run command and return its asynchronous receipt."""
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    ctx = _ctx_of(request)
    if ctx is None:
        return _err(
            "gateway boot 未加载 profile，无法执行 LCA run。",
            status_code=503,
            error_type="service_unavailable",
            code="lca_plugin_ctx_missing",
        )
    if not llm_status(ctx)["llm_available"]:
        return _err(
            "LLM_API_KEY 未配置，无法执行 LCA run。",
            status_code=503,
            error_type="service_unavailable",
            code="lca_llm_unavailable",
        )
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return _err("invalid JSON body", status_code=400)
    if not isinstance(body, dict):
        return _err("request body must be a JSON object", status_code=400)

    messages = body.get("messages") or []
    if not isinstance(messages, list):
        return _err("messages must be an array", status_code=400)

    model = str(body.get("mode") or body.get("model") or "solo")
    run_input = await prepare_run_from_messages(messages, _file_store_of(request))
    if not run_input.user_text.strip():
        return _err("messages must include a non-empty user message", status_code=400)

    try:
        mode = resolve_profile_mode(ctx, model)
    except MissingCapabilityError:
        return _err(
            "gateway profile is missing the required run_mode_registry capability.",
            status_code=503,
            error_type="service_unavailable",
            code="lca_run_mode_registry_missing",
        )

    adapter = _run_port_of(request)
    agent = parse_agent_ref(body.get("agent"))
    receipt = await adapter.create_and_dispatch(
        RunRequest(
            profile=str(body.get("profile") or "web-standard"),
            question=run_input.question,
            user_text=run_input.user_text,
            mode=mode,
            attachment_ids=run_input.attachment_ids,
            prior_turns=run_input.prior_turns,
            agent=agent,
            device_id=str(body.get("device_id") or ""),
            plane=str(body.get("plane") or ""),
            extra_plane=str(body.get("extra_plane") or ""),
            execution_target=str(body.get("execution_target") or body.get("executionTarget") or ""),
            options=dict(body.get("options") or {}),
            ctx=ctx,
        )
    )
    if not receipt.accepted:
        return _err(receipt.rejection_reason or "run creation rejected", status_code=400)
    return JSONResponse(
        {
            "run_id": receipt.run_id,
            "trace_id": receipt.trace_id,
            "agent": {"id": agent.agent_id, "name": agent.name},
            "live_url": f"/runs/{receipt.run_id}/live",
        },
        status_code=202,
        headers=cors_headers(),
    )


async def cancel_run(request: Request) -> JSONResponse:
    """POST /runs/{run_id}/cancel — forward cancellation through the run owner."""
    run_id = request.path_params["run_id"]
    receipt = await _run_port_of(request).cancel(run_id)
    if not receipt.accepted:
        return JSONResponse(
            {"error": receipt.error or "run not found"},
            status_code=receipt.error_status,
            headers=cors_headers(),
        )
    return JSONResponse({"status": receipt.status or "canceled"}, headers=cors_headers())


async def answer_run(request: Request) -> JSONResponse:
    """POST /runs/{run_id}/answer — adapt one durable approval resume command."""
    run_id = request.path_params["run_id"]
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400, headers=cors_headers())

    approval_id = str(body.get("approval_id", "")).strip()
    payload = str(body.get("payload", "")).strip()
    idempotency_key = str(body.get("idempotency_key", "")).strip()
    if not approval_id or not payload or not idempotency_key:
        return JSONResponse(
            {"error": "approval_id, payload and idempotency_key are required"},
            status_code=400,
            headers=cors_headers(),
        )
    receipt = await _run_port_of(request).resume_approval(
        run_id,
        approval_id,
        payload,
        idempotency_key,
    )
    if not receipt.accepted:
        return JSONResponse(
            {"error": receipt.error or "approval resume rejected"},
            status_code=receipt.error_status,
            headers=cors_headers(),
        )
    return JSONResponse(
        {"run_id": run_id, "status": receipt.status or "resumed"},
        headers=cors_headers(),
    )


__all__ = ["answer_run", "cancel_run", "create_run"]
