"""New /v1/sessions/* API routes — pure carrier, no business logic.

This module is a thin HTTP carrier. It only imports Starlette and
the command/projection contracts (N4: never import layer1/layer2/layer3).
"""

from __future__ import annotations

import json
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route, Router


def create_session_router(gateway: Any) -> Router:
    """Create Starlette router for /v1/sessions/* endpoints.

    All routes delegate to CommandGateway — no business logic here.
    """

    async def handle_create_session(request: Request) -> JSONResponse:
        from lca.contracts.harness.command import SessionCreateCommand

        body: dict[str, Any] = await request.json()
        cmd = SessionCreateCommand(
            idempotency_key=body.get("idempotency_key", ""),
            profile=body.get("profile", "web-standard"),
            preset=body.get("preset"),
            agent_options=body.get("options"),
        )
        gw = request.app.state.command_gateway
        receipt = await gw.handle_create_session(cmd)
        return JSONResponse(
            status_code=201,
            content={
                "session_id": receipt.session_id,
                "seq": receipt.seq,
                "accepted": receipt.accepted,
            },
        )

    async def handle_send_message(request: Request) -> JSONResponse:
        from lca.contracts.harness.command import MessageSendCommand

        session_id = request.path_params["session_id"]
        body = await request.json()
        cmd = MessageSendCommand(
            idempotency_key=body.get("idempotency_key", ""),
            session_id=session_id,
            role="user",
            content=body["content"],
            attachments=tuple(body.get("attachments", ())),
        )
        gw = request.app.state.command_gateway
        receipt = await gw.handle_send_message(cmd)
        return JSONResponse(
            content={
                "session_id": receipt.session_id,
                "seq": receipt.seq,
                "accepted": receipt.accepted,
            }
        )

    async def handle_snapshot(request: Request) -> JSONResponse:
        session_id = request.path_params["session_id"]
        gw = request.app.state.command_gateway
        snapshot = await gw.get_snapshot(session_id)
        return JSONResponse(
            content={
                "as_of_seq": snapshot.as_of_seq,
                "values": snapshot.values,
            }
        )

    async def handle_sse_events(request: Request) -> StreamingResponse:
        session_id = request.path_params["session_id"]
        last_seq = int(request.query_params.get("last_seq", "0"))
        gw = request.app.state.command_gateway

        async def event_stream():
            async for change in gw.subscribe_changes(session_id, last_seq):
                data = json.dumps(
                    {
                        "key": change.key,
                        "seq": change.seq,
                        "version": change.version,
                        "value": change.value,
                    }
                )
                yield f"event: projection\ndata: {data}\n\n".encode("utf-8")

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
        )

    async def handle_answer(request: Request) -> JSONResponse:
        from lca.contracts.harness.command import AnswerCommand

        session_id = request.path_params["session_id"]
        body = await request.json()
        cmd = AnswerCommand(session_id=session_id, answer=body["answer"])
        gw = request.app.state.command_gateway
        receipt = await gw.handle_answer(cmd)
        return JSONResponse(content={"accepted": receipt.accepted})

    async def handle_cancel(request: Request) -> JSONResponse:
        from lca.contracts.harness.command import CancelCommand

        session_id = request.path_params["session_id"]
        body = await request.json()
        cmd = CancelCommand(
            session_id=session_id,
            keep_inbox=body.get("keep_inbox", True),
        )
        gw = request.app.state.command_gateway
        receipt = await gw.handle_cancel(cmd)
        return JSONResponse(content={"accepted": receipt.accepted})

    async def handle_steer(request: Request) -> JSONResponse:
        from lca.contracts.harness.command import SteerCommand

        session_id = request.path_params["session_id"]
        body = await request.json()
        cmd = SteerCommand(session_id=session_id, content=body["content"])
        gw = request.app.state.command_gateway
        receipt = await gw.handle_steer(cmd)
        return JSONResponse(content={"accepted": receipt.accepted})

    return Router(
        routes=[
            Route("/sessions", handle_create_session, methods=["POST"]),
            Route(
                "/sessions/{session_id}/messages",
                handle_send_message,
                methods=["POST"],
            ),
            Route(
                "/sessions/{session_id}/snapshot",
                handle_snapshot,
                methods=["GET"],
            ),
            Route(
                "/sessions/{session_id}/events",
                handle_sse_events,
                methods=["GET"],
            ),
            Route(
                "/sessions/{session_id}/commands/answer",
                handle_answer,
                methods=["POST"],
            ),
            Route(
                "/sessions/{session_id}/commands/cancel",
                handle_cancel,
                methods=["POST"],
            ),
            Route(
                "/sessions/{session_id}/commands/steer",
                handle_steer,
                methods=["POST"],
            ),
        ]
    )
