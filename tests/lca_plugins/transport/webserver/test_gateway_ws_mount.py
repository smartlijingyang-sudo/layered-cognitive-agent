"""Tests for lca-gateway-ws-mount plugin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from starlette.applications import Starlette

from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.ws import (
    mount_ws_route,
)


@dataclass
class _FakeHandle:
    app: Starlette


class _FakeCtx:
    def __init__(self, handle: _FakeHandle) -> None:
        self._handle = handle

    def require(self, key: str) -> Any:
        assert key == "web_server"
        return self._handle


@pytest.mark.asyncio
async def test_gateway_ws_mount_plugin_appends_websocket_route() -> None:
    from lca.plugins.transport.webserver.routes_2.routes_agent_gateway_ws import (
        setup as plugin,
    )

    app = Starlette(routes=[])
    handle = _FakeHandle(app=app)
    ctx = _FakeCtx(handle)
    await plugin.setup(ctx, None)
    ws_paths = [
        getattr(route, "path", None)
        for route in app.router.routes
        if route.__class__.__name__ == "WebSocketRoute"
    ]
    assert "/v1/runs/{run_id}/ws" in ws_paths


def test_mount_ws_route_duplicate_path_raises() -> None:
    app = Starlette(routes=[])

    async def _noop(ws: Any) -> None:
        await ws.accept()
        await ws.close()

    mount_ws_route(app, handler=_noop)
    try:
        mount_ws_route(app, handler=_noop)
        raised = False
    except RuntimeError:
        raised = True
    assert raised
