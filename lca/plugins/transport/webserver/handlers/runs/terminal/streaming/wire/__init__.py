"""LcaAgentGateway wire — route catalog + WS mount + supporting HTTP handlers.

This subpackage is the plugin integration seam for the agent runtime
WebSocket bridge (ADR-0200 / Agent Note 2026-09-07). The HTTP route
catalog is declared as :class:`RouteSpec` so the existing
``register_routes`` machinery picks it up. The WebSocket route is
declared in the same ``ROUTE_SPECS`` tuple for documentation /
discovery but is mounted via :func:`mount_ws_route` because Starlette
WebSocketRoute is a separate type from HTTP ``Route``.
"""
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.http import (
    build_http_app,
    get_running_operation,
    refresh_ws_token,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.routes import (
    ROUTE_SPECS,
    WS_PATH,
    WS_ROUTE_SPEC,
    WS_TOKEN_PATH,
    RUNNING_OP_PATH,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.ws import (
    mount_ws_route,
)

__all__ = (
    "ROUTE_SPECS",
    "RUNNING_OP_PATH",
    "WS_PATH",
    "WS_ROUTE_SPEC",
    "WS_TOKEN_PATH",
    "build_http_app",
    "get_running_operation",
    "mount_ws_route",
    "refresh_ws_token",
)
