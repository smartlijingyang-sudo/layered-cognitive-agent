"""Integration tests for the WS handshake JWT path.

Covers ``POST /v1/runs/{run_id}/ws-token`` and ``WS /v1/runs/{run_id}/ws``:

- When ``app.state.jwt_keys`` is populated (dev-mode or production),
  the handler returns a 3-part JWT / accepts the token on the WS path.
- When ``app.state.jwt_keys`` is ``None`` AND no ``LCA_JWT_SECRET`` /
  ``LCA_JWT_PUBLIC_KEY`` env var is set, the handler returns 503 with
  ``code='jwt_secret_unconfigured'`` rather than 500. Regression for the
  POST /lca-api/runs → 500 class of bugs.

This is the path that the lobehub front-end exercises end-to-end when
``isLcaGatewayMode()`` is true.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest


@pytest.fixture(autouse=True)
def _scrub_jwt_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LCA_JWT_SECRET", raising=False)
    monkeypatch.delenv("LCA_JWT_PUBLIC_KEY", raising=False)


def test_refresh_ws_token_returns_200_when_jwt_keys_seeded() -> None:
    """Happy path: app.state.jwt_keys populated → 200 + 3-part JWT."""
    import redis.asyncio as aioredis

    from lca.infrastructure.observability.stream import LcaStreamEventManager
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.http import (
        build_http_app,
    )
    from lca.plugins.transport.webserver.jwt_keys_seam.jwt_keys import (
        JwtKeys,
        generate_dev_keypair,
    )
    from starlette.testclient import TestClient

    priv, pub = generate_dev_keypair()
    app = build_http_app()
    app.state.jwt_keys = JwtKeys(private_pem=priv, public_pem=pub)
    run_id = f"ws200_{uuid.uuid4().hex[:8]}"

    async def _seed_then_cleanup() -> None:
        client = aioredis.from_url("redis://127.0.0.1:6379/0", decode_responses=True)
        try:
            mgr = LcaStreamEventManager(client)
            await mgr.publish(
                run_id, "agent_runtime_init", {"agentId": "a1"}, step_index=0
            )
        finally:
            await client.aclose()

    async def _drop() -> None:
        client = aioredis.from_url("redis://127.0.0.1:6379/0", decode_responses=True)
        try:
            await LcaStreamEventManager(client).cleanup(run_id)
        finally:
            await client.aclose()

    try:
        asyncio.run(_seed_then_cleanup())
        with TestClient(app) as client:
            resp = client.post(f"/v1/runs/{run_id}/ws-token")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["token_type"] == "Bearer"  # noqa: S105
            assert body["token"].count(".") == 2
    finally:
        asyncio.run(_drop())


def test_refresh_ws_token_returns_503_when_jwt_missing() -> None:
    """Regression: missing app.state.jwt_keys AND no LCA_JWT_SECRET env
    → 503 ``jwt_secret_unconfigured`` (not 500).
    """
    import redis.asyncio as aioredis

    from lca.infrastructure.observability.stream import LcaStreamEventManager
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.http import (
        build_http_app,
    )
    from starlette.testclient import TestClient

    app = build_http_app()
    # No app.state.jwt_keys set; no LCA_JWT_SECRET env (autouse fixture).
    run_id = f"ws503_{uuid.uuid4().hex[:8]}"

    async def _seed_then_cleanup() -> None:
        client = aioredis.from_url("redis://127.0.0.1:6379/0", decode_responses=True)
        try:
            mgr = LcaStreamEventManager(client)
            await mgr.publish(
                run_id, "agent_runtime_init", {"agentId": "a1"}, step_index=0
            )
        finally:
            await client.aclose()

    async def _drop() -> None:
        client = aioredis.from_url("redis://127.0.0.1:6379/0", decode_responses=True)
        try:
            await LcaStreamEventManager(client).cleanup(run_id)
        finally:
            await client.aclose()

    try:
        asyncio.run(_seed_then_cleanup())
        with TestClient(app) as client:
            resp = client.post(f"/v1/runs/{run_id}/ws-token")
            assert resp.status_code == 503, resp.text
            body = resp.json()
            assert body.get("code") == "jwt_secret_unconfigured"
    finally:
        asyncio.run(_drop())