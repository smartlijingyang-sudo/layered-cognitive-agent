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
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from starlette.applications import Starlette

from starlette.requests import Request
from starlette.responses import JSONResponse

from lca.cognition.team.modes_catalog import resolve_profile_mode
from lca.contracts.models.core.conversation.conversation import ConversationTurn
from lca.infrastructure.file.store import LocalFileStore
from lca.plugins.transport.webserver.handlers.cors.cors import cors_headers
from lca.plugins.transport.webserver.handlers.runs.ingest.ingress.ingress import (
    LobeHubRunInput,
    prepare_run_from_messages,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.port.port import (
    RunPort,
    RunReceipt,
    RunRequest,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.gateway_lifecycle import (
    topic_id_from_body,
)
from lca.plugins.transport.webserver.read.runs.identity.identity import (
    AgentRef,
    parse_agent_ref,
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
    run_id: str = ""
    """精准指定要恢复的 run_id，避免并发/多轮时 topic 最新指针漂移导致的 409 Conflict。"""
    resume_approval: dict[str, Any] | None = None
    """Gap C: front-end ``LcaStartRunBody.resume_approval`` (deploy patch).
    Non-``None`` ⇒ POST is an approval-resume of a paused run; ``create_run``
    routes it to ``RunPort.resume_approval`` instead of ``create_and_dispatch``."""
    resume_tool_result: dict[str, Any] | None = None
    """Gap C: front-end ``LcaStartRunBody.resume_tool_result`` (deploy patch).
    Non-``None`` ⇒ POST is a tool-result resume; the human answer is forwarded
    to ``RunPort.resume_approval`` as ``payload`` + ``plugin_state`` so the
    existing paused run continues from ``phase: 'tool_result'``."""


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

    resume_approval = _decode_resume_approval(body.get("resume_approval"))
    if isinstance(resume_approval, JSONResponse):
        return resume_approval
    resume_tool_result = _decode_resume_tool_result(body.get("resume_tool_result"))
    if isinstance(resume_tool_result, JSONResponse):
        return resume_tool_result

    run_input: LobeHubRunInput = await prepare_run_from_messages(messages, file_store)
    if resume_approval is None and resume_tool_result is None and not run_input.user_text.strip():
        return _err("messages must include a non-empty user message", status_code=400)

    run_id_raw = body.get("run_id")
    run_id = str(run_id_raw).strip() if run_id_raw is not None else ""

    return CreateRunRequest(
        profile=str(body.get("profile") or "web-assistant"),
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
        run_id=run_id,
        resume_approval=resume_approval,
        resume_tool_result=resume_tool_result,
    )


def _decode_resume_approval(raw: Any) -> dict[str, Any] | JSONResponse | None:
    """Normalize ``resume_approval`` body field (camelCase keys).

    Returns the dict on success, ``None`` when the field is absent, or a
    JSON 400 response when the field is present but malformed.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return _err(
            "resume_approval must be an object", status_code=400, code="invalid_resume_approval"
        )
    approval_id = str(raw.get("approvalId") or raw.get("approval_id") or "").strip()
    tool_call_id = str(raw.get("toolCallId") or raw.get("tool_call_id") or "").strip()
    rejection_reason = raw.get("rejectionReason") or raw.get("rejection_reason")
    if not approval_id and not tool_call_id:
        return _err(
            "resume_approval requires approvalId or toolCallId",
            status_code=400,
            code="invalid_resume_approval",
        )
    return {
        "approval_id": approval_id or tool_call_id,
        "tool_call_id": tool_call_id,
        "parent_message_id": str(raw.get("parentMessageId") or raw.get("parent_message_id") or ""),
        "rejection_reason": str(rejection_reason) if rejection_reason is not None else "",
    }


def _decode_resume_tool_result(raw: Any) -> dict[str, Any] | JSONResponse | None:
    """Normalize ``resume_tool_result`` body field (camelCase keys).

    Returns the dict on success, ``None`` when the field is absent, or a
    JSON 400 response when the field is present but malformed.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return _err(
            "resume_tool_result must be an object",
            status_code=400,
            code="invalid_resume_tool_result",
        )
    tool_call_id = str(raw.get("toolCallId") or raw.get("tool_call_id") or "").strip()
    content = raw.get("content")
    if not tool_call_id:
        return _err(
            "resume_tool_result requires toolCallId",
            status_code=400,
            code="invalid_resume_tool_result",
        )
    if not isinstance(content, str):
        return _err(
            "resume_tool_result.content must be a string",
            status_code=400,
            code="invalid_resume_tool_result",
        )
    plugin_state_raw = raw.get("pluginState")
    plugin_state: dict[str, Any] | None
    if plugin_state_raw is None or plugin_state_raw == {}:
        plugin_state = None
    elif isinstance(plugin_state_raw, dict):
        plugin_state = plugin_state_raw
    else:
        return _err(
            "resume_tool_result.pluginState must be an object",
            status_code=400,
            code="invalid_resume_tool_result",
        )
    return {
        "tool_call_id": tool_call_id,
        "parent_message_id": str(raw.get("parentMessageId") or raw.get("parent_message_id") or ""),
        "content": content,
        "plugin_state": plugin_state,
    }


async def _decode_json_body(request: Request) -> dict[str, Any] | JSONResponse:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return _err("invalid JSON body", status_code=400)
    if not isinstance(body, dict):
        return _err("request body must be a JSON object", status_code=400)
    return body


def render_create_run_receipt(
    receipt: RunReceipt,
    agent: AgentRef,
    *,
    jwt_keys: Any | None = None,
) -> JSONResponse:
    """Format a :class:`RunReceipt` to the 202 compatibility envelope.

    P1 (§5.6.1) adds ``ws_token`` so the front-end can open the WS
    gateway immediately. The legacy keys (``run_id``, ``trace_id``,
    ``agent``, ``live_url``) are preserved byte-compat.
    ``register_gateway_run`` (called from :func:`create_run`) writes
    the running-operation row and publishes ``agent_runtime_init``.

    `jwt_keys` is the resolved :class:`lca.plugins.transport.webserver.jwt_keys_seam.JwtKeys`
    instance installed on ``request.app.state.jwt_keys`` by the webserver
    bootstrap. When it is missing (Profile did not provide one and
    ``jwt.dev_mode`` is false) we return 503 ``jwt_secret_unconfigured``
    rather than letting ``mint_user_jwt`` raise and surface as 500.
    """
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import (
        DEFAULT_TTL_SECONDS,
        JwtSecretUnconfiguredError,
        mint_user_jwt,
    )

    private_pem = getattr(jwt_keys, "private_pem", None) if jwt_keys is not None else None
    try:
        ws_token = mint_user_jwt(
            user_id=str(agent.agent_id or "lca-local"),
            operation_id=receipt.run_id,
            private_key_pem=private_pem,
            ttl_seconds=DEFAULT_TTL_SECONDS,
        )
    except JwtSecretUnconfiguredError as exc:
        return _err(str(exc), status_code=503, code="jwt_secret_unconfigured")
    return JSONResponse(
        {
            "run_id": receipt.run_id,
            "trace_id": receipt.trace_id,
            "agent": {"id": agent.agent_id, "name": agent.name},
            "live_url": f"/runs/{receipt.run_id}/live",
            "ws_token": ws_token,
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
        from lca.plugins.assistant.home._home_layout import (
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


def _validate_assistant_ownership(request: Request, assistant_id: str) -> JSONResponse | None:
    """ADR-0252 I-4：带 ``assistant_id`` 的 run 归属检查。

    - 无绑定 / 无用户头 / ``dev_mode`` ⇒ ``None``（遗留路径与 CLI/host
      sidecar 路径不变，I-A1）；
    - 归属已知且非请求者 ⇒ 403（fail-closed，不静默回落默认助理）。
    """
    if not assistant_id:
        return None
    from lca.plugins.transport.webserver.handlers.auth.user import auth_config_of

    _, dev_mode = auth_config_of(request)
    if dev_mode:
        return None
    user_id = request.headers.get("x-lca-user-id", "").strip()
    if not user_id:
        return None
    ownership = getattr(request.app.state, "assistant_ownership", None)
    if ownership is None:
        return None
    owner = ownership.owner_of(assistant_id)
    if owner is not None and owner != user_id:
        return _err(
            "assistant not owned by caller",
            status_code=403,
            code="assistant_not_owned",
        )
    return None


async def create_run(request: Request) -> JSONResponse:
    """``POST /runs`` — dispatch a run command and return its async receipt.

    Thin orchestrator:parse body → decode carrier request → dispatch via
    ``RunPort`` → render receipt. Capability readiness lives in the routes
    plugin and the LLM-resolver plugin, not here.

    Resume routing (Gap C): when the body carries ``resume_approval`` or
    ``resume_tool_result`` the request is an HIL resume of an existing
    paused run. ``create_run`` looks up the run by ``topic_id`` via
    ``running_operation_store`` and forwards the human answer through
    :meth:`RunPort.resume_approval` instead of dispatching a fresh run.
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

    ownership_error = _validate_assistant_ownership(request, decoded.assistant_id)
    if ownership_error is not None:
        return ownership_error

    if decoded.resume_approval is not None or decoded.resume_tool_result is not None:
        return await _dispatch_resume(request, body, decoded)

    receipt = await _run_port_of(request).create_and_dispatch(_to_run_request(decoded))
    if not receipt.accepted:
        return _err(receipt.rejection_reason or "run creation rejected", status_code=400)

    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.gateway_lifecycle import (
        register_gateway_run,
    )

    await register_gateway_run(
        request,
        run_id=receipt.run_id,
        topic_id=topic_id_from_body(body),
        agent_id=str(decoded.agent.agent_id or "solo"),
        body=body,
    )
    jwt_keys = getattr(request.app.state, "jwt_keys", None)
    return render_create_run_receipt(receipt, decoded.agent, jwt_keys=jwt_keys)


async def _dispatch_resume(
    request: Request,
    body: dict[str, Any],
    decoded: CreateRunRequest,
) -> JSONResponse:
    """Route a resume body to :meth:`RunPort.resume_approval`.

    Prefers explicit ``run_id`` from the request / payload; falls back to
    looking up the existing run via ``running_operation_store`` keyed by
    ``topic_id`` when ``run_id`` is not supplied.
    """
    payload_dict = decoded.resume_tool_result or decoded.resume_approval or {}
    run_id = (
        decoded.run_id or str(payload_dict.get("run_id") or "") or str(body.get("run_id") or "")
    ).strip()

    store = getattr(request.app.state, "running_operation_store", None)

    if not run_id:
        topic_id = topic_id_from_body(body)
        if not topic_id:
            return _err(
                "resume requires run_id or topic_id to locate the existing run",
                status_code=400,
                code="missing_topic_id",
            )
        if store is None:
            return _err("running operation store not available", status_code=503)
        row = await store.get_latest_for_topic(topic_id)
        if row is None:
            return _err(
                f"no running operation for topic {topic_id!r}",
                status_code=404,
                code="run_not_found",
            )
        run_id = str(row.get("run_id") or "").strip()
        if not run_id:
            return _err("running operation row missing run_id", status_code=500)

    approval_id = str(payload_dict.get("tool_call_id") or payload_dict.get("approval_id") or "")
    if not approval_id:
        return _err(
            "resume payload missing toolCallId/approvalId",
            status_code=400,
            code="invalid_resume_payload",
        )
    content = str(payload_dict.get("content") or payload_dict.get("rejection_reason") or "")
    plugin_state = payload_dict.get("plugin_state")
    parent_message_id = str(payload_dict.get("parent_message_id") or "")
    idempotency_key = f"{run_id}:{approval_id}:resume:{parent_message_id or 'topic'}"

    receipt = await _run_port_of(request).resume_approval(
        run_id,
        approval_id,
        content,
        idempotency_key,
        plugin_state=plugin_state,
        parent_message_id=parent_message_id,
    )
    if not receipt.accepted:
        return _err(
            receipt.error or "approval resume rejected",
            status_code=receipt.error_status,
        )
    if idempotency_key and store is not None and hasattr(store, "record_answer_key"):
        await store.record_answer_key(run_id, idempotency_key)
    return JSONResponse(
        {"run_id": run_id, "status": receipt.status or "resumed"},
        headers=cors_headers(),
    )


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


async def record_run_feedback(request: Request) -> JSONResponse:
    """``POST /runs/{run_id}/feedback`` — append ``feedback.record.v1`` (ADR-0189)."""
    run_id = request.path_params["run_id"]
    registry = getattr(request.app.state, "registry", None)
    get_run = getattr(registry, "get", None)
    session = get_run(run_id) if callable(get_run) else None
    if session is None:
        return JSONResponse({"error": "run not found"}, status_code=404, headers=cors_headers())
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400, headers=cors_headers())
    text = str(body.get("text") or body.get("feedback") or "").strip() or None
    rating = str(body.get("rating") or "").strip() or None
    raw_tags = body.get("tags")
    tags: tuple[str, ...] = ()
    if isinstance(raw_tags, list):
        tags = tuple(str(item).strip() for item in raw_tags if str(item).strip())
    if text is None and rating is None and not tags:
        return JSONResponse(
            {"error": "feedback requires text, rating, or tags"},
            status_code=400,
            headers=cors_headers(),
        )
    from lca.infrastructure.observability.meta_event_emit import emit_feedback_record
    from lca.infrastructure.session.emit.lifecycle_emit import resolve_run_session_writer

    emit_feedback_record(
        text=text,
        rating=rating,
        tags=tags,
        session=resolve_run_session_writer(session),
    )
    return JSONResponse({"run_id": run_id, "status": "recorded"}, headers=cors_headers())


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
    store = getattr(request.app.state, "running_operation_store", None)
    if store is not None:
        await store.record_answer_key(run_id, idempotency_key)
    return JSONResponse(
        {"run_id": run_id, "status": receipt.status or "resumed"},
        headers=cors_headers(),
    )


__all__ = [
    "CreateRunRequest",
    "answer_run",
    "build_create_run_app",
    "cancel_run",
    "create_run",
    "decode_create_run",
    "record_run_feedback",
    "render_create_run_receipt",
]


def build_create_run_app() -> Starlette:
    """Test factory mirroring the production /runs route mounting.

    The production router in :mod:`lca.plugins.transport.webserver.handlers.runs.api.routes`
    mounts ``create_run`` under ``POST /lca-api/runs``; this factory
    exposes the same handler at the bare ``/runs`` path so integration
    tests can hit it directly without standing up the whole
    composition root.
    """
    from starlette.applications import Starlette
    from starlette.routing import Route

    async def _create_run_starlette(request: Request) -> JSONResponse:
        # Re-bind so the existing implementation reads app.state from
        # the request scope (it already does).
        return await create_run(request)

    return Starlette(routes=[Route("/runs", _create_run_starlette, methods=["POST", "OPTIONS"])])
