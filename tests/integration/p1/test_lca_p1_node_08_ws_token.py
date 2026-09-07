"""L2-8: ``POST /v1/runs/{run_id}/ws-token`` mints a fresh JWT when the
run is alive, 404s when the Redis key is gone.

Wire response shape: ``{token, token_type, expires_in, issued_at}``.
"""

from __future__ import annotations

import asyncio
import uuid

import redis.asyncio as aioredis

from lca.infrastructure.observability.stream import LcaStreamEventManager
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.http import (
    build_http_app,
)


async def _seed_run(run_id: str) -> None:
    mgr = LcaStreamEventManager(aioredis.from_url("redis://127.0.0.1:6379/0", decode_responses=True))
    await mgr.publish(run_id, "agent_runtime_init", {"agentId": "a1"}, step_index=0)


async def _cleanup_run(run_id: str) -> None:
    mgr = LcaStreamEventManager(aioredis.from_url("redis://127.0.0.1:6379/0", decode_responses=True))
    await mgr.cleanup(run_id)


def test_ws_token_404_when_run_redis_key_missing() -> None:
    """A run_id with no Redis stream entry returns 404."""
    from starlette.testclient import TestClient

    with TestClient(build_http_app()) as client:
        resp = client.post(
            f"/v1/runs/{uuid.uuid4().hex}/ws-token", json={"userId": "u1"}
        )
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"] == "running_operation_not_found"


def test_ws_token_200_with_fresh_jwt_when_redis_key_alive() -> None:
    """A live run_id returns ``{token, token_type, expires_in, issued_at}``."""
    from starlette.testclient import TestClient

    run_id = f"r_{uuid.uuid4().hex[:8]}"

    async def _drive() -> None:
        await _seed_run(run_id)
        try:
            with TestClient(build_http_app()) as client:
                resp = client.post(
                    f"/v1/runs/{run_id}/ws-token",
                    json={"userId": "u1"},
                    headers={"x-lca-user-id": "u1"},
                )
                assert resp.status_code == 200, f"status {resp.status_code}: {resp.text}"
                body = resp.json()
                assert body["token"].count(".") == 2  # JWT shape
                assert body["token_type"] == "Bearer"
                assert body["expires_in"] > 0
                assert body["issued_at"] > 0
        finally:
            await _cleanup_run(run_id)

    asyncio.run(_drive())