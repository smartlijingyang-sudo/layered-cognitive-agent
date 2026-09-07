"""Route catalog for the LcaAgentGateway wire.

Two HTTP routes and one WebSocket route. The HTTP routes are declared
as :class:`RouteSpec` so the standard ``register_routes`` machinery
can mount them. The WebSocket route shares the same ``ROUTE_SPECS``
tuple for documentation and discovery (so consumers can enumerate the
full surface area), but the actual Starlette ``WebSocketRoute`` is
installed via :func:`mount_ws_route` because the standard register
machinery is HTTP-only.

Wire invariant (spec §3.2 + ADR-0200):
  - ``/v1/topics/{topic_id}/running-op`` — read-side; returns the latest
    ``lca_running_operations`` row for a topic (or null).
  - ``/v1/runs/{run_id}/ws-token`` — mint a short-lived JWT for the
    WS handshake. Gated by the live ``agent_runtime_stream:<run_id>``
    Redis key (a 404 means the run is not alive).
  - ``/v1/runs/{run_id}/ws`` — the WebSocket transport.
"""
from __future__ import annotations

from typing import Any

from lca.contracts.routing import RouteSpec

from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.http import (
    get_running_operation,
    refresh_ws_token,
)

WS_PATH: str = "/v1/runs/{run_id}/ws"
WS_TOKEN_PATH: str = "/v1/runs/{run_id}/ws-token"
RUNNING_OP_PATH: str = "/v1/topics/{topic_id}/running-op"


def _ws_placeholder(*_args: Any, **_kwargs: Any) -> None:  # pragma: no cover
    """Sentinel handler for the WebSocket path entry.

    Never invoked: the actual handler is installed as a Starlette
    ``WebSocketRoute`` via :func:`mount_ws_route`. Present only so the
    path can appear in a ``RouteSpec`` tuple.
    """
    raise RuntimeError("WS handler is mounted via mount_ws_route; not via HTTP")


# Single source of truth for the WS path. The HTTP register machinery
# will skip any RouteSpec whose handler raises on construction
# (currently it does not — see spec §3.2 / ADR-0200 §4.3); the path
# is still useful for discovery / docs.
WS_ROUTE_SPEC: RouteSpec = RouteSpec(
    path=WS_PATH,
    handler=_ws_placeholder,
    methods=("WS",),
)


ROUTE_SPECS: tuple[RouteSpec, ...] = (
    RouteSpec(
        path=RUNNING_OP_PATH,
        handler=get_running_operation,
        methods=("GET", "OPTIONS"),
    ),
    RouteSpec(
        path=WS_TOKEN_PATH,
        handler=refresh_ws_token,
        methods=("POST", "OPTIONS"),
    ),
    WS_ROUTE_SPEC,
)


__all__ = (
    "ROUTE_SPECS",
    "RUNNING_OP_PATH",
    "WS_PATH",
    "WS_ROUTE_SPEC",
    "WS_TOKEN_PATH",
)
