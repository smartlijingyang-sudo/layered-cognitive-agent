"""L2-3: ``heartbeat`` → ``heartbeat_ack``.

The gateway's ``_handle_control_frame`` echoes ``heartbeat_ack`` on
every ``heartbeat`` frame; the client uses this as a 30 s liveness
signal.

This test only verifies the frame handling logic by routing a
``heartbeat`` frame through the in-process gateway; it does NOT
require a Redis-backed history replay (which is exercised by L2-2).
"""

from __future__ import annotations

import uuid

import pytest
from starlette.testclient import TestClient

from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.agent_gateway import (
    build_agent_gateway_app,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import (
    mint_user_jwt,
)


def test_heartbeat_frame_echoes_ack(rsa_keys: dict[str, str]) -> None:
    """A ``heartbeat`` frame sent on an open WS gets back ``heartbeat_ack``."""
    app = build_agent_gateway_app()
    run_id = uuid.uuid4().hex
    token = mint_user_jwt(
        user_id="u1",
        operation_id=run_id,
        private_key_pem=rsa_keys["private"],
        ttl_seconds=60,
    )
    with TestClient(app) as client:
        with client.websocket_connect(f"/v1/runs/{run_id}/ws") as ws:
            ws.send_json({"type": "auth", "token": token})
            assert ws.receive_json() == {"type": "auth_success"}
            # Skip the resume handshake — gateway uses the next frame as
            # either resume OR (in some shapes) as the first control frame
            # the live loop processes. Send resume with no history; the
            # gateway enters the live loop and the next frame we send
            # goes through _handle_control_frame.
            ws.send_json(
                {"type": "resume", "lastEventId": "0", "wantStatus": False}
            )
            ws.send_json({"type": "heartbeat"})

            # Read frames until heartbeat_ack; collect all we see.
            for _ in range(10):
                try:
                    frame = ws.receive_json()
                except Exception:
                    break
                if frame.get("type") == "heartbeat_ack":
                    return  # success
            # If we get here, never saw heartbeat_ack — collect for debug.
            pytest.fail("heartbeat_ack not received")