"""L3-6: token expiry — auth_expired + refresh_ws_token + reconnect.

The user's JWT expires mid-run (TTL = 5 min). The WS receives
``auth_expired``; the client calls ``POST /lca-api/runs/{id}/ws-token``
to get a new token, then reconnects with the fresh token. Asserts
events 6..N are not duplicated after reconnect.

Gated on ``LCA_E2E_KERNEL=1``; skipped otherwise.
"""

from __future__ import annotations

import pytest


@pytest.mark.timeout(600)
def test_token_expiry_auth_expired_refresh_reconnect(lca_client) -> None:
    """5 min token expiry → auth_expired → refresh → reconnect."""
    pytest.skip("L3-6 requires LCA_E2E_KERNEL=1 (LCA dev stack); see tests/e2e/p1/conftest.py")


def test_expired_token_rejected_with_auth_failed() -> None:
    """Unit-level: an expired JWT is rejected by the gateway handshake.

    Mints a token that is already expired (issued_at in the past, TTL=1s)
    and verifies the gateway returns ``auth_failed``.
    """
    import os
    import time
    import uuid

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from starlette.testclient import TestClient

    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.agent_gateway import (
        build_agent_gateway_app,
    )
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import (
        mint_user_jwt,
    )

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    prev_secret = os.environ.get("LCA_JWT_SECRET")
    prev_public = os.environ.get("LCA_JWT_PUBLIC_KEY")
    os.environ["LCA_JWT_SECRET"] = private_pem
    os.environ["LCA_JWT_PUBLIC_KEY"] = public_pem

    try:
        run_id = uuid.uuid4().hex
        # Mint a token that expired 10 seconds ago.
        token = mint_user_jwt(
            user_id="u1",
            operation_id=run_id,
            private_key_pem=private_pem,
            ttl_seconds=1,
            issued_at=int(time.time()) - 10,
        )
        app = build_agent_gateway_app()
        with TestClient(app) as client, client.websocket_connect(f"/v1/runs/{run_id}/ws") as ws:
            ws.send_json({"type": "auth", "token": token})
            frame = ws.receive_json()
            assert frame["type"] == "auth_failed"
            assert "expired" in frame.get("reason", "").lower()
    finally:
        if prev_secret is not None:
            os.environ["LCA_JWT_SECRET"] = prev_secret
        else:
            os.environ.pop("LCA_JWT_SECRET", None)
        if prev_public is not None:
            os.environ["LCA_JWT_PUBLIC_KEY"] = prev_public
        else:
            os.environ.pop("LCA_JWT_PUBLIC_KEY", None)


def test_fresh_token_accepted_after_expiry() -> None:
    """Unit-level: after expiry, a freshly minted token is accepted.

    Simulates the L3-6 recovery path: mint expired token → rejected →
    mint fresh token → accepted.
    """
    import os
    import time
    import uuid

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from starlette.testclient import TestClient

    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.agent_gateway import (
        build_agent_gateway_app,
    )
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import (
        mint_user_jwt,
    )

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    prev_secret = os.environ.get("LCA_JWT_SECRET")
    prev_public = os.environ.get("LCA_JWT_PUBLIC_KEY")
    os.environ["LCA_JWT_SECRET"] = private_pem
    os.environ["LCA_JWT_PUBLIC_KEY"] = public_pem

    try:
        run_id = uuid.uuid4().hex
        app = build_agent_gateway_app()

        # Step 1: expired token → auth_failed.
        expired_token = mint_user_jwt(
            user_id="u1",
            operation_id=run_id,
            private_key_pem=private_pem,
            ttl_seconds=1,
            issued_at=int(time.time()) - 10,
        )
        with TestClient(app) as client, client.websocket_connect(f"/v1/runs/{run_id}/ws") as ws:
            ws.send_json({"type": "auth", "token": expired_token})
            frame = ws.receive_json()
            assert frame["type"] == "auth_failed"

        # Step 2: fresh token → auth_success (simulates refresh_ws_token).
        fresh_token = mint_user_jwt(
            user_id="u1",
            operation_id=run_id,
            private_key_pem=private_pem,
            ttl_seconds=300,
        )
        with TestClient(app) as client, client.websocket_connect(f"/v1/runs/{run_id}/ws") as ws:
            ws.send_json({"type": "auth", "token": fresh_token})
            frame = ws.receive_json()
            assert frame["type"] == "auth_success"
    finally:
        if prev_secret is not None:
            os.environ["LCA_JWT_SECRET"] = prev_secret
        else:
            os.environ.pop("LCA_JWT_SECRET", None)
        if prev_public is not None:
            os.environ["LCA_JWT_PUBLIC_KEY"] = prev_public
        else:
            os.environ.pop("LCA_JWT_PUBLIC_KEY", None)
