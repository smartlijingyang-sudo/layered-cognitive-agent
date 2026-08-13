"""Browser attaches to a Console session. Translates UI frames <-> book."""

from __future__ import annotations

import asyncio

from starlette.websockets import WebSocket, WebSocketDisconnect

from gateway.console.sessions import ConsoleBook, DeviceOfflineError
from gateway.presence.registry import PresenceRegistry
from gateway.presence.wire import PTY_EXIT, PTY_OUTPUT


async def attach_session(websocket: WebSocket) -> None:
    session_id = websocket.path_params["session_id"]
    presence: PresenceRegistry = websocket.app.state.presence
    book: ConsoleBook = websocket.app.state.consoles
    session = book.get(session_id)
    if session is None:
        await websocket.close(code=4404)
        return
    await websocket.accept()

    async def pump_output() -> None:
        while True:
            item = await session.output.get()
            if item is None:
                await websocket.send_json({"type": "exit", "code": -1})
                break
            kind = item.get("type")
            if kind == PTY_OUTPUT:
                await websocket.send_json({"type": "output", "data": item.get("data", "")})
            elif kind == PTY_EXIT:
                await websocket.send_json({"type": "exit", "code": item.get("exit_code", 0)})
                break

    pump = asyncio.create_task(pump_output())
    try:
        while True:
            msg = await websocket.receive_json()
            if not isinstance(msg, dict):
                continue
            kind = msg.get("type")
            if kind == "input":
                await book.send_input(presence, session, str(msg.get("data") or ""))
            elif kind == "resize":
                await book.resize(
                    presence,
                    session,
                    int(msg.get("cols") or 80),
                    int(msg.get("rows") or 24),
                )
    except (WebSocketDisconnect, DeviceOfflineError):
        pass
    finally:
        pump.cancel()
        await book.close(presence, session_id)
