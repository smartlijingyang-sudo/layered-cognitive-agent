"""Host sidecar attaches here. Presence handshake only; PTY frames go to ConsoleBook."""

from __future__ import annotations

import hmac
from typing import Any

import structlog
from starlette.websockets import WebSocket, WebSocketDisconnect

from gateway.console.sessions import ConsoleBook
from gateway.presence.models import CAP_CONSOLE, Device
from gateway.presence.registry import PresenceRegistry
from gateway.presence.wire import (
    EXEC_RESULT,
    HELLO,
    PING,
    PONG,
    PTY_EXIT,
    PTY_OUTPUT,
    WELCOME,
)

_log = structlog.get_logger(__name__)


class WebSocketChannel:
    def __init__(self, websocket: WebSocket) -> None:
        self._ws = websocket

    async def send(self, payload: dict[str, Any]) -> None:
        await self._ws.send_json(payload)


async def connect_host(websocket: WebSocket) -> None:
    await websocket.accept()
    presence: PresenceRegistry = websocket.app.state.presence
    consoles: ConsoleBook = websocket.app.state.consoles
    expected: str = websocket.app.state.host_token
    subject: str = websocket.app.state.host_subject

    try:
        hello = await websocket.receive_json()
    except WebSocketDisconnect:
        return
    if not isinstance(hello, dict) or hello.get("type") != HELLO:
        await websocket.close(code=4400)
        return
    token = str(hello.get("token") or "")
    if not expected or not hmac.compare_digest(token, expected):
        await websocket.close(code=4403)
        return
    device_id = str(hello.get("device_id") or "").strip()
    if not device_id:
        await websocket.close(code=4400)
        return
    caps_raw = hello.get("capabilities") or [CAP_CONSOLE]
    capabilities = tuple(str(c) for c in caps_raw if str(c).strip())
    name = str(hello.get("name") or device_id)
    device = Device(
        device_id=device_id,
        subject=subject,
        name=name,
        capabilities=capabilities or (CAP_CONSOLE,),
        platform=str(hello.get("platform") or ""),
        home=str(hello.get("home") or ""),
        root=str(hello.get("root") or ""),
    )
    channel = WebSocketChannel(websocket)
    presence.online(device, channel)
    await websocket.send_json({"type": WELCOME, "device_id": device_id})
    _log.info("host_online", device_id=device_id, name=name)
    try:
        while True:
            msg = await websocket.receive_json()
            if not isinstance(msg, dict):
                continue
            kind = msg.get("type")
            if kind == PONG:
                presence.touch(device_id)
            elif kind == PING:
                await websocket.send_json({"type": PONG})
            elif kind in {PTY_OUTPUT, PTY_EXIT}:
                consoles.ingest(msg)
            elif kind == EXEC_RESULT:
                websocket.app.state.exec_hub.complete(msg)
    except WebSocketDisconnect:
        pass
    finally:
        if presence.channel(device_id) is channel:
            websocket.app.state.exec_hub.fail_all(f"host {device_id} offline")
            presence.offline(device_id)
            consoles.close_device(device_id)
            _log.info("host_offline", device_id=device_id)
