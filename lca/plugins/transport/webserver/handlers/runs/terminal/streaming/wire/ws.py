"""WebSocket mount helper for the LcaAgentGateway wire.

The HTTP route catalog (:class:`ROUTE_SPECS`) is mounted by the
standard ``register_routes`` machinery. The WebSocket route is a
separate Starlette type (``WebSocketRoute``) and must be appended to
the Starlette ``app.router.routes`` directly. ``mount_ws_route`` is
that seam.

The handler is the same one used by
:func:`lca.plugins.transport.webserver.handlers.runs.terminal.streaming.agent_gateway.build_agent_gateway_app`
— tests inject a fake ``run_port`` via the app factory and pass the
resulting handler here.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.applications import Starlette
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket

from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.routes import (
    WS_PATH,
)

WebSocketHandler = Callable[[WebSocket], Awaitable[None]]


def mount_ws_route(
    app: Starlette,
    *,
    handler: WebSocketHandler,
    path: str = WS_PATH,
) -> WebSocketRoute:
    """Append a WebSocketRoute to ``app`` and return the new route.

    Duplicate paths raise (Starlette's default behaviour). The
    returned route is the actual ``WebSocketRoute`` instance, useful
    for test introspection.
    """
    route = WebSocketRoute(path, handler)
    app.router.routes.append(route)
    return route


__all__ = ("WebSocketHandler", "mount_ws_route")
