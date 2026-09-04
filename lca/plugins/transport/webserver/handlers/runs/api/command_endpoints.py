"""HTTP command handlers for the run carrier (ADR-0163 决策 2 + 5).

Thin glue:

- :func:`decode_create_run` decodes JSON body, validates shape, and yields a
  :class:`lca.plugins.transport.webserver.handlers.runs.api.command_endpoints.CreateRunRequest`
  pre-validated dataclass.
- :func:`render_create_run_receipt` formats a :class:`RunReceipt` to the
  202 JSON envelope.
- :func:`create_run` orchestrates ``_decode ∘ RunPort.create_and_dispatch ∘ _render``.

Responsibility of the carrier is reduced to three mechanical steps.
Boot-period readiness guards (LLM key, ctx presence, mode registry) are
checked in routes plugin registration (``RouteSpec.requires``) and in
the ``lca-llm-resolver`` plugin setup.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from starlette.requests import Request
from starlette.responses import JSONResponse

from lca.cognition.team.modes_catalog import resolve_profile_mode
from lca.contracts.models.core.conversation import ConversationTurn
from lca.infrastructure.file_store import LocalFileStore
from lca.plugins.transport.webserver.handlers.cors import cors_headers
from lca.plugins.transport.webserver.handlers.runs.ingest.ingress import (
    LobeHubRunInput,
    prepare_run_from_messages,
)
from lca.plugins.transport.webserver.handlers.runs.observability.identity import (
    AgentRef,
    parse_agent_ref,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.port import (
    RunPort,
    RunReceipt,
    RunRequest,
)


def _file_store_of(request: Request) -> LocalFileStore:
    return cast("LocalFileStore", request.app.state.file_store)


def _run_port_of(request: Request) -> RunPort:
    """Return the single run owner selected by the composition root."""
    return cast("RunPort", request.app.state.run_port)


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


@dataclass(frozen=True)
class CreateRunRequest:
    """Decoded ``POST /runs`` body, validated for handler-side shape only.

    The carrier no longer probes boot-period concerns (mode registry, LLM
    availability). Those are responsibilities of the composition root or
    the routes plugin registration. The carrier handles payload shape and
    4xx-shaped errors here.
    """

    profile: str
    question: str
    user_text: str
    mode: str
    attachment_ids: tuple[str, ...]
    prior_turns: tuple[ConversationTurn, ...]
    agent: AgentRef
    device_id: str
    plane: str
    extra_plane: str
    execution_target: str
    options: dict[str, Any]
    ctx: object
    assistant_id: str = ""
    """ADR-0187 §3 D7 一次性 run 绑定（``asst_*``）；空 = 遗留默认 agent。"""


async def decode_create_run(
    body: dict[str, Any],
    *,
    ctx: object,
    file_store: LocalFileStore,
    resolve_mode: Any,
) -> CreateRunRequest | JSONResponse:
    """Decode + validate ``POST /runs`` body to a typed carrier request.

    Returns either a :class:`CreateRunRequest` or a JSON 4xx response. Boot
    failures (mode registry missing, LLM unavailable) propagate as
    ``MissingCapabilityError`` so registration can fail fast instead of
    producing a half-functional server.
    """
    messages = body.get("messages") or []
    if not isinstance(messages, list):
        return _err("messages must be an array", status_code=400)

    assistant_raw = body.get("assistant_id")
    if assistant_raw is None or (isinstance(assistant_raw, str) and not assistant_raw.strip()):
        assistant_id = ""
    elif isinstance(assistant_raw, str):
        assistant_id = assistant_raw.strip()
    else:
        return _err(
            f"assistant_id must be a string, got {type(assistant_raw).__name__}",
            status_code=400,
            code="invalid_assistant_id",
        )

    mode = str(body.get("mode") or body.get("model") or "solo")
    resolved_mode = resolve_mode(ctx, mode)

    run_input: LobeHubRunInput = await prepare_run_from_messages(messages, file_store)
    if not run_input.user_text.strip():
        return _err("messages must include a non-empty user message", status_code=400)

    return CreateRunRequest(
        profile=str(body.get("profile") or "web-standard"),
        question=run_input.question,
        user_text=run_input.user_text,
        mode=resolved_mode,
        attachment_ids=run_input.attachment_ids,
        prior_turns=run_input.prior_turns,
        agent=parse_agent_ref(body.get("agent")),
        device_id=str(body.get("device_id") or ""),
        plane=str(body.get("plane") or ""),
        extra_plane=str(body.get("extra_plane") or ""),
        execution_target=str(body.get("execution_target") or body.get("executionTarget") or ""),
        options=dict(body.get("options") or {}),
        ctx=ctx,
        assistant_id=assistant_id,
    )


async def _decode_json_body(request: Request) -> dict[str, Any] | JSONResponse:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return _err("invalid JSON body", status_code=400)
    if not isinstance(body, dict):
        return _err("request body must be a JSON object", status_code=400)
    return body


def render_create_run_receipt(receipt: RunReceipt, agent: AgentRef) -> JSONResponse:
    """Format a :class:`RunReceipt` to the 202 compatibility envelope."""
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


def _to_run_request(carrier: CreateRunRequest) -> RunRequest:
    """Translate carrier-decode output into the port protocol shape."""
    return RunRequest(
        profile=carrier.profile,
        question=carrier.question,
        user_text=carrier.user_text,
        mode=carrier.mode,
        attachment_ids=carrier.attachment_ids,
        prior_turns=carrier.prior_turns,
        agent=carrier.agent,
        device_id=carrier.device_id,
        plane=carrier.plane,
        extra_plane=carrier.extra_plane,
        execution_target=carrier.execution_target,
        options=carrier.options,
        ctx=carrier.ctx,
        assistant_id=carrier.assistant_id,
    )


def _validate_assistant_binding(request: Request, assistant_id: str) -> JSONResponse | None:
    """Fail-closed 校验 run 的 assistant 绑定（ADR-0187 §3 D7）。

    - 无绑定 ⇒ ``None``（遗留路径逐字不变，I-A1）；
    - 有绑定但 catalog 未装配（web-standard）⇒ 400；
    - 未知 id ⇒ 404；digest 不匹配 ⇒ 409（唯一恢复路径 = reimport）。
    """
    if not assistant_id:
        return None
    catalog = getattr(request.app.state, "assistant_catalog", None)
    if catalog is None:
        return _err(
            "assistant capability not enabled on this profile",
            status_code=400,
            code="assistant_unavailable",
        )
    try:
        catalog.get(assistant_id)
    except Exception as exc:
        from lca.plugins.assistant._home_layout import (
            AssistantCatalogError,
            AssistantDigestMismatch,
        )

        if isinstance(exc, AssistantDigestMismatch):
            return _err(
                f"assistant {assistant_id!r} 配置面 digest 不一致",
                status_code=409,
                code="digest_mismatch",
            )
        if isinstance(exc, AssistantCatalogError):
            return _err(str(exc), status_code=404, code="assistant_not_found")
        return _err(str(exc), status_code=500, code="internal_error")
    return None


async def create_run(request: Request) -> JSONResponse:
    """``POST /runs`` — dispatch a run command and return its async receipt.

    Thin orchestrator:parse body → decode carrier request → dispatch via
    ``RunPort`` → render receipt. Capability readiness lives in the routes
    plugin and the LLM-resolver plugin, not here.
    """
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await _decode_json_body(request)
    if isinstance(body, JSONResponse):
        return body

    ctx = getattr(request.app.state, "ctx", None)
    decoded = await decode_create_run(
        body,
        ctx=ctx,
        file_store=_file_store_of(request),
        resolve_mode=resolve_profile_mode,
    )
    if isinstance(decoded, JSONResponse):
        return decoded

    binding_error = _validate_assistant_binding(request, decoded.assistant_id)
    if binding_error is not None:
        return binding_error

    receipt = await _run_port_of(request).create_and_dispatch(_to_run_request(decoded))
    if not receipt.accepted:
        return _err(receipt.rejection_reason or "run creation rejected", status_code=400)
    return render_create_run_receipt(receipt, decoded.agent)


async def cancel_run(request: Request) -> JSONResponse:
    """``POST /runs/{run_id}/cancel`` — forward cancellation through the run owner."""
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
    """``POST /runs/{run_id}/answer`` — adapt one durable approval resume command."""
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


__all__ = [
    "CreateRunRequest",
    "answer_run",
    "cancel_run",
    "create_run",
    "decode_create_run",
    "render_create_run_receipt",
]
