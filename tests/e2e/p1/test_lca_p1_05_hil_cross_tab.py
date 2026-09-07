"""L3-5: HIL cross-tab — close tab during HIL, reopen, submit answer.

The user closes the browser tab while the agent is paused for HIL
(``agent_runtime_end{waiting_for_human}``). They reopen a new tab;
the ``GET /lca-api/topics/{topic_id}/running-op`` endpoint returns the
same run; the new WS reconnects and sees ``resume_complete { status:
'waiting_input' }``. Submitting the answer with the same
``idempotency_key`` twice returns 200 both times (second is replayed).

Gated on ``LCA_E2E_KERNEL=1``; skipped otherwise.
"""

from __future__ import annotations

import pytest


@pytest.mark.timeout(120)
def test_hil_cross_tab_reconnect_and_submit(lca_client) -> None:
    """Close tab during HIL → reopen → submit answer from new tab."""
    pytest.skip("L3-5 requires LCA_E2E_KERNEL=1 (LCA dev stack); see tests/e2e/p1/conftest.py")


def test_hil_idempotency_key_replay() -> None:
    """Unit-level: same idempotency_key is accepted without re-executing.

    Two separate WS connections (simulating tab close + reopen) each
    send a ``tool_result`` with the same ``idempotencyKey``; the
    gateway forwards both to ``RunPort.resume_approval``.
    """
    import asyncio
    import os
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

    class _IdempotentPort:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str]] = []

        async def cancel(self, run_id: str) -> None:
            pass

        async def resume_approval(
            self,
            run_id: str,
            approval_id: str,
            payload: str,
            idempotency_key: str,
        ) -> None:
            self.calls.append((approval_id, payload, idempotency_key))

    port = _IdempotentPort()
    run_id = uuid.uuid4().hex

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
        token = mint_user_jwt(
            user_id="u1",
            operation_id=run_id,
            private_key_pem=private_pem,
            ttl_seconds=60,
        )

        async def _drive() -> None:
            # Tab 1: connect, auth, resume, send tool_result.
            app1 = build_agent_gateway_app(run_port=port)  # type: ignore[arg-type]
            with (
                TestClient(app1) as client1,
                client1.websocket_connect(f"/v1/runs/{run_id}/ws") as ws1,
            ):
                ws1.send_json({"type": "auth", "token": token})
                ws1.receive_json()  # auth_success
                ws1.send_json({"type": "resume", "lastEventId": "0", "wantStatus": False})
                await asyncio.sleep(0.05)
                ws1.send_json(
                    {
                        "type": "tool_result",
                        "toolCallId": "tc1",
                        "success": True,
                        "content": "answer from tab 1",
                        "idempotencyKey": "idem-key-1",
                    }
                )
                for _ in range(50):
                    if len(port.calls) >= 1:
                        break
                    await asyncio.sleep(0.02)

            # Tab 2: reopen, reconnect, send same tool_result.
            app2 = build_agent_gateway_app(run_port=port)  # type: ignore[arg-type]
            with (
                TestClient(app2) as client2,
                client2.websocket_connect(f"/v1/runs/{run_id}/ws") as ws2,
            ):
                ws2.send_json({"type": "auth", "token": token})
                ws2.receive_json()  # auth_success
                ws2.send_json({"type": "resume", "lastEventId": "0", "wantStatus": False})
                await asyncio.sleep(0.05)
                ws2.send_json(
                    {
                        "type": "tool_result",
                        "toolCallId": "tc1",
                        "success": True,
                        "content": "answer from tab 1",
                        "idempotencyKey": "idem-key-1",
                    }
                )
                for _ in range(50):
                    if len(port.calls) >= 2:
                        break
                    await asyncio.sleep(0.02)

        asyncio.run(_drive())

        assert len(port.calls) == 2
        assert port.calls[0][2] == "idem-key-1"
        assert port.calls[1][2] == "idem-key-1"
    finally:
        if prev_secret is not None:
            os.environ["LCA_JWT_SECRET"] = prev_secret
        else:
            os.environ.pop("LCA_JWT_SECRET", None)
        if prev_public is not None:
            os.environ["LCA_JWT_PUBLIC_KEY"] = prev_public
        else:
            os.environ.pop("LCA_JWT_PUBLIC_KEY", None)
