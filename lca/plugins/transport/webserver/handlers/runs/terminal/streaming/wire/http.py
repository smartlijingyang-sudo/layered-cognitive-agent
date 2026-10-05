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

from lca.contracts.observability.registry.status import RunLifecycleStatus
from lca.infrastructure.observability.stream import (
    LcaStreamEventLog,
    get_agent_runtime_redis_client,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import (
    DEFAULT_TTL_SECONDS,
    JwtSecretUnconfiguredError,
    mint_user_jwt,
)


def _stream_manager() -> LcaStreamEventLog:
    """Per-request stream manager.

    A module-level instance would bind its async Redis client to the
    event loop that first imported it; that loop closes between tests,
    which would surface as ``RuntimeError: Event loop is closed``. The
    factory keeps the manager scoped to the active loop.
    """
    return LcaStreamEventLog(get_agent_runtime_redis_client())


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
    if row is None:
        return JSONResponse({"running_operation": None})

    from lca.plugins.transport.webserver.handlers.auth.user import auth_config_of

    run_id = row.get("run_id") if isinstance(row, dict) else None
    registry = getattr(request.app.state, "registry", None)
    session = registry.get(run_id) if (run_id and registry and hasattr(registry, "get")) else None

    # lca_running_operations has no status column and its rows are never deleted,
    # so the latest row for a topic is usually a run that ended long ago. Liveness
    # lives only in the registry. Answering with a dead run makes every caller
    # attach to a stream that will never emit, which is worse than answering null.
    # An empty registry after a restart reads as "nothing live", which is true.
    if RunLifecycleStatus.is_terminal(getattr(session, "status", None)):
        return JSONResponse({"running_operation": None})

    _, dev_mode = auth_config_of(request)
    if not dev_mode:
        caller_user_id = request.headers.get("x-lca-user-id", "").strip()
        if run_id:
            owner_user_id = getattr(session, "user_id", "") if session is not None else ""
            if not owner_user_id:
                mgr = _stream_manager()
                init_event = await mgr.get_init_event(run_id)
                if init_event:
                    owner_user_id = (init_event.get("data") or {}).get("userId") or ""
            if owner_user_id and owner_user_id != caller_user_id:
                return JSONResponse({"running_operation": None})

    return JSONResponse({"running_operation": row})


async def refresh_ws_token(request: Request) -> JSONResponse:
    """Mint a fresh JWT for the WS handshake if the run is alive.

    404 → Redis key ``agent_runtime_stream:<run_id>`` does not exist
    (the run is not registered with the LcaAgentRuntimeCoordinator or
    has been torn down).
    200 → ``{"token": "<jwt>", "expires_in": <seconds>, "token_type": "Bearer"}``.
    503 → JWT signing key is not configured
    (Profile missing ``jwt.private_pem`` and ``jwt.dev_mode`` is false).
    """
    run_id = request.path_params.get("run_id", "")
    if not run_id:
        return JSONResponse({"error": "missing run_id"}, status_code=400)
    mgr = _stream_manager()
    if not await mgr.exists(run_id):
        return JSONResponse(
            {"error": "running_operation_not_found", "run_id": run_id},
            status_code=404,
        )

    from lca.plugins.transport.webserver.handlers.auth.user import auth_config_of

    _, dev_mode = auth_config_of(request)
    caller_user_id = request.headers.get("x-lca-user-id", "").strip()

    if not dev_mode:
        if not caller_user_id:
            return JSONResponse(
                {"error": "missing x-lca-user-id header", "code": "missing_user"},
                status_code=401,
            )
        registry = getattr(request.app.state, "registry", None)
        session = registry.get(run_id) if (registry and hasattr(registry, "get")) else None
        owner_user_id = getattr(session, "user_id", "") if session is not None else ""
        if not owner_user_id:
            init_event = await mgr.get_init_event(run_id)
            if init_event:
                owner_user_id = (init_event.get("data") or {}).get("userId") or ""
        if owner_user_id and owner_user_id != caller_user_id:
            return JSONResponse(
                {"error": "run not owned by caller", "code": "run_not_owned"},
                status_code=403,
            )
        user_id = caller_user_id
    else:
        user_id = caller_user_id or f"ws-token-{uuid.uuid4().hex[:8]}"

    jwt_keys = getattr(request.app.state, "jwt_keys", None)
    private_pem = getattr(jwt_keys, "private_pem", None) if jwt_keys is not None else None
    try:
        token = mint_user_jwt(
            user_id=user_id,
            operation_id=run_id,
            private_key_pem=private_pem,
            ttl_seconds=DEFAULT_TTL_SECONDS,
        )
    except JwtSecretUnconfiguredError as exc:
        return JSONResponse(
            {"error": str(exc), "code": "jwt_secret_unconfigured"},
            status_code=503,
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
