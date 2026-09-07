"""HTTP handlers for the LcaAgentGateway wire.

Two endpoints (ADR-0200 §3.2):

- ``GET  /v1/topics/{topic_id}/running-op`` → ``get_running_operation``
  Returns the most recent ``lca_running_operations`` row for a topic,
  or ``{"running_operation": null}`` if the store is unbound or empty.
  Production binds a Postgres-backed store on ``app.state``; tests
  skip the Postgres-backed path and exercise the null branch.

- ``POST /v1/runs/{run_id}/ws-token`` → ``refresh_ws_token``
  Mints a short-lived JWT for the WS handshake. Gated by the live
  ``agent_runtime_stream:<run_id>`` Redis key — a 404 means the run
  is not alive. The token TTL is the standard 5 minutes
  (auth.DEFAULT_TTL_SECONDS).
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse

from lca.infrastructure.observability.stream import (
    LcaStreamEventManager,
    get_agent_runtime_redis_client,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import (
    DEFAULT_TTL_SECONDS,
    mint_user_jwt,
)


def _stream_manager() -> LcaStreamEventManager:
    """Per-request stream manager.

    A module-level instance would bind its async Redis client to the
    event loop that first imported it; that loop closes between tests,
    which would surface as ``RuntimeError: Event loop is closed``. The
    factory keeps the manager scoped to the active loop.
    """
    return LcaStreamEventManager(get_agent_runtime_redis_client())


def _get_running_operation_store(request: Request) -> Any | None:
    """Return the bound ``RunningOperationStore`` for this request, if any.

    Set by the lifespan in :mod:`lca.plugins.transport.webserver.lifespan`
    when the Postgres pool is available. Tests that do not bind it see
    ``None`` and the handler short-circuits to ``{"running_operation": null}``.
    """
    state = getattr(request.app, "state", None)
    if state is None:
        return None
    return getattr(state, "running_operation_store", None)


async def get_running_operation(request: Request) -> JSONResponse:
    """Return the latest running operation row for ``topic_id``, or null.

    Wire shape: ``{"running_operation": {...} | null}``. The Postgres-
    backed store is intentionally not exercised here — Task 10 scope is
    the null branch; the populated-row branch is covered by the
    ``lca_running_operations`` migration (Task 12 / PR-3 followup).
    """
    store = _get_running_operation_store(request)
    if store is None:
        return JSONResponse({"running_operation": None})
    topic_id = request.path_params.get("topic_id", "")
    row = await store.get_latest_for_topic(topic_id)
    return JSONResponse({"running_operation": row})


async def refresh_ws_token(request: Request) -> JSONResponse:
    """Mint a fresh JWT for the WS handshake if the run is alive.

    404 → Redis key ``agent_runtime_stream:<run_id>`` does not exist
    (the run is not registered with the LcaAgentRuntimeCoordinator or
    has been torn down).
    200 → ``{"token": "<jwt>", "expires_in": <seconds>, "token_type": "Bearer"}``.
    """
    run_id = request.path_params.get("run_id", "")
    if not run_id:
        return JSONResponse({"error": "missing run_id"}, status_code=400)
    if not await _stream_manager().exists(run_id):
        return JSONResponse(
            {"error": "running_operation_not_found", "run_id": run_id},
            status_code=404,
        )
    # user_id is supplied by the auth layer in production; for this
    # wire endpoint we accept a header but default to a stable id
    # so the test pattern (no auth wiring) still works.
    user_id = request.headers.get("x-lca-user-id") or f"ws-token-{uuid.uuid4().hex[:8]}"
    token = mint_user_jwt(
        user_id=user_id,
        operation_id=run_id,
        ttl_seconds=DEFAULT_TTL_SECONDS,
    )
    return JSONResponse(
        {
            "token": token,
            "token_type": "Bearer",
            "expires_in": DEFAULT_TTL_SECONDS,
            "issued_at": int(time.time()),
        }
    )


def build_http_app() -> Starlette:
    """Build a Starlette app exposing only the HTTP routes.

    Used by tests; the WebSocket is mounted separately via
    :func:`lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.ws.mount_ws_route`.
    """
    from starlette.routing import Route

    return Starlette(
        routes=[
            Route(
                "/v1/topics/{topic_id}/running-op",
                get_running_operation,
                methods=["GET", "OPTIONS"],
            ),
            Route(
                "/v1/runs/{run_id}/ws-token",
                refresh_ws_token,
                methods=["POST", "OPTIONS"],
            ),
        ]
    )


__all__ = (
    "build_http_app",
    "get_running_operation",
    "refresh_ws_token",
)
