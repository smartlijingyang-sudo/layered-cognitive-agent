"""Gateway HTTP surface: route ownership and request-to-state adapters.

This module owns the public route catalog and the small adapters that translate
Starlette requests into injected gateway state. Business behavior remains in
its domain-specific endpoint modules; the composition root only assembles the
application and its dependencies.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route, WebSocketRoute

from gateway.cors import CORS_HEADERS
from gateway.device_gateway.routes import (
    agent_run as device_agent_run,
)
from gateway.device_gateway.routes import (
    connect_device,
    device_status,
)
from gateway.device_gateway.routes import (
    list_devices as list_gateway_devices,
)
from gateway.device_gateway.routes import (
    rpc as device_rpc,
)
from gateway.device_gateway.routes import (
    system_info as device_system_info,
)
from gateway.device_gateway.routes import (
    tool_call as device_tool_call,
)
from gateway.device_gateway.routes import (
    upload_files as device_upload_files,
)
from gateway.files import download_file, get_file_meta
from gateway.openai_shim import (
    chat_completions,
    embeddings_create,
    list_models,
    responses_create,
)
from gateway.runs.api.command_endpoints import answer_run, cancel_run, create_run
from gateway.runs.api.query_endpoints import (
    get_context,
    get_run,
    get_run_doctor,
    get_run_evidence,
    get_run_profile,
    health_payload,
    stream_journal_live,
    stream_run_live,
)
from gateway.session_routes import (
    command_answer,
    command_cancel,
    command_inject,
    command_steer,
    create_session,
    get_snapshot,
    send_message,
    stream_events,
)


async def health(request: Request) -> JSONResponse:
    """Report health from the run owner and device registry selected by composition."""
    payload = health_payload(
        request.app.state.run_port,
        ctx=getattr(request.app.state, "ctx", None),
    )
    payload["devices"] = request.app.state.devices.summary()
    return JSONResponse(payload, headers=CORS_HEADERS)


async def _download_file(request: Request) -> Response:
    return await download_file(request, request.app.state.file_store)


async def _get_file_meta(request: Request) -> JSONResponse:
    return await get_file_meta(request, request.app.state.file_store)


async def _options(_request: Request) -> JSONResponse:
    return JSONResponse({}, headers=CORS_HEADERS)


def build_routes() -> list[Route | WebSocketRoute]:
    """Return the complete, classified public gateway route catalog."""
    return [
        Route("/health", health, methods=["GET"]),
        Route("/context", get_context, methods=["GET", "OPTIONS"]),
        Route("/journal/live", stream_journal_live, methods=["GET", "OPTIONS"]),
        Route("/runs", create_run, methods=["POST", "OPTIONS"]),
        Route("/runs/{run_id}", get_run, methods=["GET"]),
        Route("/runs/{run_id}/live", stream_run_live, methods=["GET", "OPTIONS"]),
        Route("/runs/{run_id}/doctor", get_run_doctor, methods=["GET"]),
        Route("/runs/{run_id}/profile", get_run_profile, methods=["GET"]),
        Route("/runs/{run_id}/evidence/{ref:path}", get_run_evidence, methods=["GET"]),
        Route("/runs/{run_id}/cancel", cancel_run, methods=["POST", "OPTIONS"]),
        Route("/runs/{run_id}/answer", answer_run, methods=["POST", "OPTIONS"]),
        Route("/v1/sessions", create_session, methods=["POST", "OPTIONS"]),
        Route("/v1/sessions/{session_id}/messages", send_message, methods=["POST", "OPTIONS"]),
        Route("/v1/sessions/{session_id}/snapshot", get_snapshot, methods=["GET", "OPTIONS"]),
        Route("/v1/sessions/{session_id}/events", stream_events, methods=["GET", "OPTIONS"]),
        Route(
            "/v1/sessions/{session_id}/commands/answer", command_answer, methods=["POST", "OPTIONS"]
        ),
        Route(
            "/v1/sessions/{session_id}/commands/cancel", command_cancel, methods=["POST", "OPTIONS"]
        ),
        Route(
            "/v1/sessions/{session_id}/commands/steer", command_steer, methods=["POST", "OPTIONS"]
        ),
        Route(
            "/v1/sessions/{session_id}/commands/inject", command_inject, methods=["POST", "OPTIONS"]
        ),
        Route("/files/{attachment_id}", _download_file, methods=["GET"]),
        Route("/files/{attachment_id}/meta", _get_file_meta, methods=["GET"]),
        Route("/v1/models", list_models, methods=["GET", "OPTIONS"]),
        Route("/v1/chat/completions", chat_completions, methods=["POST", "OPTIONS"]),
        Route("/v1/embeddings", embeddings_create, methods=["POST", "OPTIONS"]),
        Route("/v1/responses", responses_create, methods=["POST", "OPTIONS"]),
        Route("/api/device/status", device_status, methods=["POST", "OPTIONS"]),
        Route("/api/device/devices", list_gateway_devices, methods=["POST", "OPTIONS"]),
        Route("/api/device/tool-call", device_tool_call, methods=["POST", "OPTIONS"]),
        Route("/api/device/system-info", device_system_info, methods=["POST", "OPTIONS"]),
        Route("/api/device/rpc", device_rpc, methods=["POST", "OPTIONS"]),
        Route("/api/device/agent/run", device_agent_run, methods=["POST", "OPTIONS"]),
        Route("/api/device/files/upload", device_upload_files, methods=["POST", "OPTIONS"]),
        WebSocketRoute("/api/device/ws", connect_device),
        Route("/runs/{run_id}/cancel", _options, methods=["OPTIONS"]),
        Route("/runs/{run_id}/answer", _options, methods=["OPTIONS"]),
    ]
