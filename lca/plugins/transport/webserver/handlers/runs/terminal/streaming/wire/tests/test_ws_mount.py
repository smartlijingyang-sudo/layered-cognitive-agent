"""Smoke test for the WebSocket mount seam.

Task 11: confirm ``mount_ws_route`` is reachable from the streaming
package init (``lca.plugins.transport.webserver.handlers.runs.terminal.streaming``)
and that an empty Starlette app with a mounted fake handler is
dial-able from a TestClient.
"""
from __future__ import annotations

from starlette.applications import Starlette
from starlette.testclient import TestClient
from starlette.websockets import WebSocket

from lca.plugins.transport.webserver.handlers.runs.terminal.streaming import (
    mount_ws_route as reexported_mount_ws_route,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.ws import (
    mount_ws_route,
)


def test_mount_ws_route_reexported_from_streaming_init() -> None:
    """The re-export is the same function as the wire package symbol."""
    assert reexported_mount_ws_route is mount_ws_route


def test_empty_app_with_mounted_handler_is_dialable() -> None:
    """A bare Starlette app with one mounted fake handler accepts a WS."""
    received: list[str] = []

    async def fake_handler(ws: WebSocket) -> None:
        await ws.accept()
        msg = await ws.receive_text()
        received.append(msg)
        await ws.send_text(f"got:{msg}")
        await ws.close()

    app = Starlette()
    route = mount_ws_route(app, handler=fake_handler)
    assert route.path == "/v1/runs/{run_id}/ws"

    with TestClient(app) as client:
        with client.websocket_connect("/v1/runs/probe-1/ws") as ws:
            ws.send_text("ping")
            assert ws.receive_text() == "got:ping"

    assert received == ["ping"]
