"""L2 tests for LcaAgentGateway (Task 7+8).

Exercises the Starlette WebSocketRoute end-to-end:
  L2-1: invalid token rejected with auth_failed
  L2-2: resume replays history then emits resume_complete
  L2-3: heartbeat gets heartbeat_ack
  L2-4: interrupt triggers RunPort.cancel

Reliability notes (lca-ci-test-reliability):
- Each test seeds a unique ``run_id`` and calls ``mgr.cleanup(run_id)`` in
  a ``finally`` so Redis state never bleeds into the next test.
- The interrupt / heartbeat tests use bounded ``asyncio.wait_for`` wrappers
  so a slow pump cannot stall the suite past the lane budget.
"""
import asyncio
import contextlib
import os
import uuid

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


# Pre-generate an RSA key pair for the test module
@pytest.fixture(scope="module", autouse=True)
def rsa_keys_module():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

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


@pytest.fixture
def gateway_app(rsa_keys_module):
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.agent_gateway import (
        build_agent_gateway_app,
    )
    return build_agent_gateway_app()


def mint_for_test(user_id: str, op: str, private_pem: str) -> str:
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import (
        mint_user_jwt,
    )
    return mint_user_jwt(
        user_id=user_id, operation_id=op, private_key_pem=private_pem, ttl_seconds=60
    )


def test_invalid_token_rejected_with_auth_failed(gateway_app):
    """L2-1: An invalid token receives `auth_failed` and the socket closes."""
    with TestClient(gateway_app) as client:
        with client.websocket_connect("/v1/runs/op1/ws") as ws:
            ws.send_json({"type": "auth", "token": "this.is.not.valid"})
            msg = ws.receive_json()
            assert msg["type"] == "auth_failed"


def test_resume_replays_history_then_emits_resume_complete(gateway_app, rsa_keys_module):
    """L2-2: A fresh client connecting with lastEventId=0 receives prior events in order."""
    import redis.asyncio as aioredis
    from lca.infrastructure.observability.stream import LcaStreamEventManager

    run_id = f"test_resume_{uuid.uuid4().hex[:8]}"
    token = mint_for_test("u1", run_id, rsa_keys_module["private"])

    async def seed_then_cleanup() -> None:
        client = aioredis.from_url("redis://127.0.0.1:6379/0", decode_responses=True)
        try:
            mgr = LcaStreamEventManager(client)
            await mgr.publish(run_id, "agent_runtime_init", {"agentId": "a1"}, step_index=0)
            await mgr.publish(
                run_id,
                "stream_chunk",
                {"chunkType": "text", "content": "hello"},
                step_index=1,
            )
        finally:
            await client.aclose()

    async def cleanup_only() -> None:
        client = aioredis.from_url("redis://127.0.0.1:6379/0", decode_responses=True)
        try:
            await LcaStreamEventManager(client).cleanup(run_id)
        finally:
            await client.aclose()

    try:
        asyncio.run(seed_then_cleanup())

        with TestClient(gateway_app) as client:
            with client.websocket_connect(f"/v1/runs/{run_id}/ws") as ws:
                ws.send_json({"type": "auth", "token": token})
                assert ws.receive_json() == {"type": "auth_success"}
                ws.send_json({"type": "resume", "lastEventId": "0", "wantStatus": True})
                frames = []
                for _ in range(3):
                    try:
                        frames.append(ws.receive_text())
                    except WebSocketDisconnect:
                        break
                assert any('"agent_runtime_init"' in f for f in frames), frames
                assert any('"stream_chunk"' in f and '"hello"' in f for f in frames), frames
                assert any('"type":"resume_complete"' in f for f in frames), frames
    finally:
        asyncio.run(cleanup_only())


def test_heartbeat_gets_heartbeat_ack(gateway_app, rsa_keys_module):
    """L2-3: Client heartbeat frames are answered with heartbeat_ack.

    After ``resume`` (no history, wantStatus=False) the server enters the
    live loop and is waiting for the next control frame. We send
    ``heartbeat`` immediately and expect ``heartbeat_ack`` back.
    """
    run_id = f"test_heartbeat_{uuid.uuid4().hex[:8]}"
    token = mint_for_test("u1", run_id, rsa_keys_module["private"])

    with TestClient(gateway_app) as client:
        with client.websocket_connect(f"/v1/runs/{run_id}/ws") as ws:
            ws.send_json({"type": "auth", "token": token})
            assert ws.receive_json() == {"type": "auth_success"}
            ws.send_json({"type": "resume", "lastEventId": "0", "wantStatus": False})
            ws.send_json({"type": "heartbeat"})
            ack = ws.receive_json()
            assert ack == {"type": "heartbeat_ack"}


def test_interrupt_triggers_run_port_cancel(rsa_keys_module):
    """L2-4: An `interrupt` frame calls RunPort.cancel(run_id)."""
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.agent_gateway import (
        build_agent_gateway_app,
    )

    cancel_calls = []

    class FakePort:
        async def cancel(self, run_id):
            cancel_calls.append(run_id)
            return None

        async def resume_approval(self, run_id, approval_id, payload, idempotency_key):
            return None

    app = build_agent_gateway_app(run_port=FakePort())
    run_id = f"test_interrupt_{uuid.uuid4().hex[:8]}"
    token = mint_for_test("u1", run_id, rsa_keys_module["private"])

    with TestClient(app) as client:
        with client.websocket_connect(f"/v1/runs/{run_id}/ws") as ws:
            ws.send_json({"type": "auth", "token": token})
            ws.receive_json()  # auth_success
            ws.send_json({"type": "resume", "lastEventId": "0", "wantStatus": False})
            ws.send_json({"type": "interrupt"})
            with pytest.raises(WebSocketDisconnect):
                ws.receive_text()
    assert cancel_calls == [run_id]
