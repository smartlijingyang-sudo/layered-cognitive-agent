"""HTTP carrier for /v1/sessions. Imports command/projection contracts + gateway."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, cast

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from gateway.cors import CORS_HEADERS
from lca.contracts.atoms.ids import new_id
from lca.contracts.harness.command import (
    AnswerCommand,
    CancelCommand,
    InjectCommand,
    MessageSendCommand,
    SessionCreateCommand,
    SteerCommand,
)
from lca.harness.command.gateway import CommandGateway


def _gateway(request: Request) -> CommandGateway:
    gw = getattr(request.app.state, "command_gateway", None)
    if gw is None:
        raise RuntimeError("session spine is not bound")
    return cast("CommandGateway", gw)


async def create_session(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=CORS_HEADERS)
    body: dict[str, Any] = await request.json()
    receipt = await _gateway(request).handle_create_session(
        SessionCreateCommand(
            idempotency_key=str(body.get("idempotency_key") or new_id("idem")),
            profile=str(body.get("profile") or "web-standard"),
            preset=body.get("preset"),
            agent_options=body.get("agent_options"),
        )
    )
    return JSONResponse(
        {
            "command_id": receipt.command_id,
            "session_id": receipt.session_id,
            "seq": receipt.seq,
            "accepted": receipt.accepted,
            "rejection_reason": receipt.rejection_reason,
        },
        status_code=201 if receipt.accepted else 400,
        headers=CORS_HEADERS,
    )


async def send_message(request: Request) -> JSONResponse:
    session_id = request.path_params["session_id"]
    body: dict[str, Any] = await request.json()
    receipt = await _gateway(request).handle_send_message(
        MessageSendCommand(
            idempotency_key=str(body.get("idempotency_key") or new_id("idem")),
            session_id=session_id,
            role="user",
            content=str(body.get("content") or ""),
        )
    )
    return JSONResponse(
        {
            "command_id": receipt.command_id,
            "session_id": receipt.session_id,
            "seq": receipt.seq,
            "accepted": receipt.accepted,
            "rejection_reason": receipt.rejection_reason,
        },
        headers=CORS_HEADERS,
    )


async def get_snapshot(request: Request) -> JSONResponse:
    session_id = request.path_params["session_id"]
    snapshot = await _gateway(request).get_snapshot(session_id)
    return JSONResponse(
        {"session_id": session_id, "as_of_seq": snapshot.as_of_seq, "values": snapshot.values},
        headers=CORS_HEADERS,
    )


async def stream_events(request: Request) -> StreamingResponse:
    session_id = request.path_params["session_id"]
    last_seq = 0
    raw = request.headers.get("last-event-id")
    if raw and raw.isdigit():
        last_seq = int(raw)

    async def event_stream() -> AsyncIterator[str]:
        async for change in _gateway(request).subscribe_changes(session_id, last_seq):
            payload = {
                "session_id": change.session_id,
                "key": change.key,
                "version": change.version,
                "seq": change.seq,
                "value": change.value,
            }
            yield f"id: {change.seq}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=CORS_HEADERS)


async def command_answer(request: Request) -> JSONResponse:
    session_id = request.path_params["session_id"]
    body: dict[str, Any] = await request.json()
    receipt = await _gateway(request).handle_answer(
        AnswerCommand(session_id=session_id, answer=str(body.get("answer") or ""))
    )
    return JSONResponse(
        {
            "accepted": receipt.accepted,
            "seq": receipt.seq,
            "session_id": receipt.session_id,
        },
        headers=CORS_HEADERS,
    )


async def command_cancel(request: Request) -> JSONResponse:
    session_id = request.path_params["session_id"]
    body: dict[str, Any] = {}
    if request.headers.get("content-type", "").startswith("application/json"):
        body = await request.json()
    receipt = await _gateway(request).handle_cancel(
        CancelCommand(session_id=session_id, keep_inbox=bool(body.get("keep_inbox", True)))
    )
    return JSONResponse({"accepted": receipt.accepted, "seq": receipt.seq}, headers=CORS_HEADERS)


async def command_steer(request: Request) -> JSONResponse:
    session_id = request.path_params["session_id"]
    body: dict[str, Any] = await request.json()
    receipt = await _gateway(request).handle_steer(
        SteerCommand(session_id=session_id, content=str(body.get("content") or ""))
    )
    return JSONResponse({"accepted": receipt.accepted, "seq": receipt.seq}, headers=CORS_HEADERS)


async def command_inject(request: Request) -> JSONResponse:
    session_id = request.path_params["session_id"]
    body: dict[str, Any] = await request.json()
    receipt = await _gateway(request).handle_inject(
        InjectCommand(
            session_id=session_id,
            source=str(body.get("source") or "system"),
            content=str(body.get("content") or ""),
        )
    )
    return JSONResponse({"accepted": receipt.accepted, "seq": receipt.seq}, headers=CORS_HEADERS)
