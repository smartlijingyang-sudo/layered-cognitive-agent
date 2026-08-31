"""Starlette transport adapter for the session command gateway.

Routes translate HTTP requests into harness commands and delegate execution to
``CommandGateway``. Wire-format construction lives in ``session_payloads`` so
this module has one responsibility: transport orchestration.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from lca.contracts.atoms.ids import new_id
from lca.contracts.harness.act.command import (
    ApprovalResumeCommand,
    CancelCommand,
    InjectCommand,
    MessageSendCommand,
    SessionCreateCommand,
    SteerCommand,
)
from lca.harness.command.gateway import CommandGateway
from lca.plugins.transport.webserver.handlers.cors import CORS_HEADERS
from lca.plugins.transport.webserver.handlers.session_payloads import (
    accepted_receipt_payload,
    command_receipt_payload,
    snapshot_payload,
    sse_change_payload,
)


def _gateway(request: Request) -> CommandGateway:
    gw = getattr(request.app.state, "command_gateway", None)
    if gw is None:
        raise RuntimeError("session spine is not bound")
    return cast("CommandGateway", gw)


def _json_response(payload: dict[str, Any], *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code, headers=CORS_HEADERS)


def _session_id(request: Request) -> str:
    return str(request.path_params["session_id"])


def _last_event_seq(request: Request) -> int:
    raw = request.headers.get("last-event-id")
    return int(raw) if raw and raw.isdigit() else 0


async def create_session(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return _json_response({})
    body: dict[str, Any] = await request.json()
    receipt = await _gateway(request).handle_create_session(
        SessionCreateCommand(
            idempotency_key=str(body.get("idempotency_key") or new_id("idem")),
            profile=str(body.get("profile") or "web-standard"),
            preset=body.get("preset"),
            agent_options=body.get("agent_options"),
        )
    )
    return _json_response(
        command_receipt_payload(receipt), status_code=201 if receipt.accepted else 400
    )


async def send_message(request: Request) -> JSONResponse:
    body: dict[str, Any] = await request.json()
    receipt = await _gateway(request).handle_send_message(
        MessageSendCommand(
            idempotency_key=str(body.get("idempotency_key") or new_id("idem")),
            session_id=_session_id(request),
            role="user",
            content=str(body.get("content") or ""),
        )
    )
    return _json_response(command_receipt_payload(receipt))


async def get_snapshot(request: Request) -> JSONResponse:
    session_id = _session_id(request)
    snapshot = await _gateway(request).get_snapshot(session_id)
    return _json_response(snapshot_payload(session_id, snapshot))


async def stream_events(request: Request) -> StreamingResponse:
    session_id = _session_id(request)
    last_seq = _last_event_seq(request)

    async def event_stream() -> AsyncIterator[str]:
        async for change in _gateway(request).subscribe_changes(session_id, last_seq):
            yield sse_change_payload(change)

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=CORS_HEADERS)


async def command_answer(request: Request) -> JSONResponse:
    body: dict[str, Any] = await request.json()
    receipt = await _gateway(request).handle_resume_approval(
        ApprovalResumeCommand(
            session_id=_session_id(request),
            approval_id=str(body.get("approval_id") or ""),
            payload=str(body.get("payload") or ""),
            idempotency_key=str(body.get("idempotency_key") or ""),
        )
    )
    return _json_response(accepted_receipt_payload(receipt))


async def command_cancel(request: Request) -> JSONResponse:
    body: dict[str, Any] = {}
    if request.headers.get("content-type", "").startswith("application/json"):
        body = await request.json()
    receipt = await _gateway(request).handle_cancel(
        CancelCommand(
            session_id=_session_id(request), keep_inbox=bool(body.get("keep_inbox", True))
        )
    )
    return _json_response(accepted_receipt_payload(receipt))


async def command_steer(request: Request) -> JSONResponse:
    body: dict[str, Any] = await request.json()
    receipt = await _gateway(request).handle_steer(
        SteerCommand(session_id=_session_id(request), content=str(body.get("content") or ""))
    )
    return _json_response(accepted_receipt_payload(receipt))


async def command_inject(request: Request) -> JSONResponse:
    body: dict[str, Any] = await request.json()
    receipt = await _gateway(request).handle_inject(
        InjectCommand(
            session_id=_session_id(request),
            source=str(body.get("source") or "system"),
            content=str(body.get("content") or ""),
        )
    )
    return _json_response(accepted_receipt_payload(receipt))
