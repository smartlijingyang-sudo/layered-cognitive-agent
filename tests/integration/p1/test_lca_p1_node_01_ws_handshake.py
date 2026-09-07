"""L2-1: WS upgrade + auth (``auth_success`` / ``auth_failed`` /
``auth_expired``).

Drives the in-process ``LcaAgentGateway`` via ``TestClient`` + a fresh
JWT minted by the test fixture's RSA keypair.
"""

from __future__ import annotations

import time
import uuid

import pytest
from starlette.testclient import TestClient

from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import (
    InvalidTokenError,
    mint_user_jwt,
    verify_user_jwt,
)


def test_auth_failed_on_invalid_token(lca_gateway_app) -> None:
    """Garbage token → server emits ``auth_failed`` and closes."""
    with TestClient(lca_gateway_app) as client:
        with client.websocket_connect(f"/v1/runs/{uuid.uuid4().hex}/ws") as ws:
            ws.send_json({"type": "auth", "token": "garbage"})
            msg = ws.receive_json()
            assert msg["type"] == "auth_failed"


def test_auth_failed_when_first_frame_is_not_auth(lca_gateway_app) -> None:
    """Server expects the first frame to be ``{type:auth}``."""
    with TestClient(lca_gateway_app) as client:
        with client.websocket_connect(f"/v1/runs/{uuid.uuid4().hex}/ws") as ws:
            ws.send_json({"type": "resume", "lastEventId": "0"})
            msg = ws.receive_json()
            assert msg["type"] == "auth_failed"
            assert "auth" in msg.get("reason", "").lower()


def test_auth_expired_raises_invalid_token_error(rsa_keys: dict[str, str]) -> None:
    """``verify_user_jwt`` raises ``InvalidTokenError`` for an expired token.

    Decoupled from the WS path so the test stays <5 s.
    """
    run_id = uuid.uuid4().hex
    token = mint_user_jwt(
        user_id="u1",
        operation_id=run_id,
        private_key_pem=rsa_keys["private"],
        ttl_seconds=1,
    )
    time.sleep(2)
    with pytest.raises(InvalidTokenError):
        verify_user_jwt(
            token,
            expected_operation_id=run_id,
            public_key_pem=rsa_keys["public"],
        )


def test_auth_success_with_fresh_token(
    lca_gateway_app, rsa_keys: dict[str, str]
) -> None:
    """Fresh token → server emits ``auth_success`` then waits for resume."""
    run_id = uuid.uuid4().hex
    token = mint_user_jwt(
        user_id="u1",
        operation_id=run_id,
        private_key_pem=rsa_keys["private"],
        ttl_seconds=60,
    )
    with TestClient(lca_gateway_app) as client:
        with client.websocket_connect(f"/v1/runs/{run_id}/ws") as ws:
            ws.send_json({"type": "auth", "token": token})
            assert ws.receive_json() == {"type": "auth_success"}
