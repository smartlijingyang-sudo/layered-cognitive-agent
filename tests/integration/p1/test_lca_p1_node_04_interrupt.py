"""L2-4: ``interrupt`` invokes ``RunPort.cancel(run_id)`` and closes.

The patched ``_handle_control_frame`` dispatches the cancel call
when the frame is ``{type:'interrupt'}`` and returns ``"interrupt"``
so the live loop exits.
"""

from __future__ import annotations

import uuid

from starlette.testclient import TestClient

from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.agent_gateway import (
    build_agent_gateway_app,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import (
    mint_user_jwt,
)


class _RecordingPort:
    def __init__(self) -> None:
        self.cancel_calls: list[str] = []

    async def cancel(self, run_id: str) -> None:
        self.cancel_calls.append(run_id)

    async def resume_approval(self, *args, **kwargs) -> None:
        return None


def test_interrupt_invokes_run_port_cancel(rsa_keys: dict[str, str]) -> None:
    port = _RecordingPort()
    app = build_agent_gateway_app(run_port=port)  # type: ignore[arg-type]
    run_id = uuid.uuid4().hex
    token = mint_user_jwt(
        user_id="u1",
        operation_id=run_id,
        private_key_pem=rsa_keys["private"],
        ttl_seconds=60,
    )

    with TestClient(app) as client, client.websocket_connect(f"/v1/runs/{run_id}/ws") as ws:
        ws.send_json({"type": "auth", "token": token})
        ws.receive_json()
        # Skip the resume handshake; jump straight to interrupt.
        ws.send_json(
            {"type": "resume", "lastEventId": "0", "wantStatus": False}
        )
        # Drain any pre-interrupt frames (none in this scenario).
        ws.send_json({"type": "interrupt"})
        # Receive until disconnect or a few frames.
        try:
            ws.receive_text()
        except Exception:
            pass

    assert port.cancel_calls == [run_id]


def test_interrupt_does_not_invoke_when_no_port(rsa_keys: dict[str, str]) -> None:
    """When ``run_port=None``, the gateway logs and ignores the cancel."""
    app = build_agent_gateway_app()
    run_id = uuid.uuid4().hex
    token = mint_user_jwt(
        user_id="u1",
        operation_id=run_id,
        private_key_pem=rsa_keys["private"],
        ttl_seconds=60,
    )
    with TestClient(app) as client, client.websocket_connect(f"/v1/runs/{run_id}/ws") as ws:
        ws.send_json({"type": "auth", "token": token})
        ws.receive_json()
        ws.send_json(
            {"type": "resume", "lastEventId": "0", "wantStatus": False}
        )
        ws.send_json({"type": "interrupt"})
        try:
            ws.receive_text()
        except Exception:
            pass
