"""HTTP handler tests for the LcaAgentGateway wire (Task 10).

L1.1: ``GET /v1/topics/{topic_id}/running-op`` returns ``{"running_operation": null}``
      when no store is bound on ``app.state`` (the production
      Postgres-backed path is out of scope for this dispatch).
L1.2: ``POST /v1/runs/{run_id}/ws-token`` returns 404 when the
      ``agent_runtime_stream:<run_id>`` Redis key is missing.
L1.3: ``POST /v1/runs/{run_id}/ws-token`` returns 200 with a 3-part
      JWT when the Redis key is alive.

Reliability: each test that touches Redis seeds a unique ``run_id``
and runs ``mgr.cleanup(run_id)`` in a ``finally`` so state does not
bleed into the next test.
"""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from starlette.testclient import TestClient

from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.http import (
    build_http_app,
)


@pytest.fixture(scope="module", autouse=True)
def rsa_keys_module():
    """Generate a fresh RSA key pair (same shape as test_lca_agent_gateway)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    os.environ["LCA_JWT_SECRET"] = private_pem
    os.environ["LCA_JWT_PUBLIC_KEY"] = public_pem
    return {"private": private_pem, "public": public_pem}


def test_get_running_operation_returns_null_for_missing_store() -> None:
    """No store bound on app.state → 200 with ``{"running_operation": null}``."""
    app = build_http_app()
    topic_id = f"t_{uuid.uuid4().hex[:8]}"
    with TestClient(app) as client:
        resp = client.get(f"/v1/topics/{topic_id}/running-op")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body == {"running_operation": None}


def test_refresh_ws_token_returns_404_when_run_redis_key_missing() -> None:
    """No live stream key → 404 with a structured error body."""
    app = build_http_app()
    run_id = f"ws404_{uuid.uuid4().hex[:8]}"
    # Make sure the key is really gone.
    import redis.asyncio as aioredis

    from lca.contracts.transport.stream_keys import stream_key

    async def _drop() -> None:
        client = aioredis.from_url("redis://127.0.0.1:6379/0", decode_responses=True)
        try:
            await client.delete(stream_key(run_id))
        finally:
            await client.aclose()

    asyncio.run(_drop())

    with TestClient(app) as client:
        resp = client.post(f"/v1/runs/{run_id}/ws-token")
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert body["error"] == "running_operation_not_found"
        assert body["run_id"] == run_id


def test_refresh_ws_token_returns_200_with_token_when_redis_key_alive() -> None:
    """Live stream key → 200 with a 3-part JWT (header.payload.signature)."""
    import redis.asyncio as aioredis

    from lca.infrastructure.observability.stream import LcaStreamEventManager

    app = build_http_app()
    run_id = f"ws200_{uuid.uuid4().hex[:8]}"

    async def _seed_then_cleanup() -> None:
        client = aioredis.from_url("redis://127.0.0.1:6379/0", decode_responses=True)
        try:
            mgr = LcaStreamEventManager(client)
            await mgr.publish(run_id, "agent_runtime_init", {"agentId": "a1"}, step_index=0)
        finally:
            await client.aclose()

    async def _drop() -> None:
        client = aioredis.from_url("redis://127.0.0.1:6379/0", decode_responses=True)
        try:
            from lca.infrastructure.observability.stream import LcaStreamEventManager
            await LcaStreamEventManager(client).cleanup(run_id)
        finally:
            await client.aclose()

    try:
        asyncio.run(_seed_then_cleanup())
        with TestClient(app) as client:
            resp = client.post(f"/v1/runs/{run_id}/ws-token")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert "token" in body
            assert body["token_type"] == "Bearer"  # noqa: S105 (token type literal)
            assert isinstance(body["expires_in"], int) and body["expires_in"] > 0
            assert len(body["token"].split(".")) == 3
    finally:
        asyncio.run(_drop())
