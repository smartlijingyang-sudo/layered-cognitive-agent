"""L2-5: ``tool_result`` forwards to ``RunPort.resume_approval``.

The patched ``_handle_control_frame`` dispatches the
``resume_approval(run_id, approval_id, payload, idempotency_key)``
call when the frame is ``{type:'tool_result', ...}`` and stays in
the live loop (the gateway does NOT close after tool_result — the
client decides when to disconnect).
"""

from __future__ import annotations

import asyncio
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
        self.calls: list[tuple[str, str, str, str]] = []

    async def cancel(self, run_id: str) -> None:
        return None

    async def resume_approval(
        self,
        run_id: str,
        approval_id: str,
        payload: str,
        idempotency_key: str,
    ) -> None:
        self.calls.append((run_id, approval_id, payload, idempotency_key))


def test_tool_result_routes_to_resume_approval(rsa_keys: dict[str, str]) -> None:
    """The handler forwards toolCallId/content/idempotencyKey to the port."""
    port = _RecordingPort()
    app = build_agent_gateway_app(run_port=port)  # type: ignore[arg-type]
    run_id = uuid.uuid4().hex
    token = mint_user_jwt(
        user_id="u1",
        operation_id=run_id,
        private_key_pem=rsa_keys["private"],
        ttl_seconds=60,
    )

    # Wait for the port to record the call asynchronously, then close.
    async def _drive() -> None:
        with TestClient(app) as client:
            with client.websocket_connect(f"/v1/runs/{run_id}/ws") as ws:
                ws.send_json({"type": "auth", "token": token})
                ws.receive_json()
                ws.send_json(
                    {"type": "resume", "lastEventId": "0", "wantStatus": False}
                )
                # Tiny sleep so the live_loop is wired up before we send tool_result.
                await asyncio.sleep(0.05)
                ws.send_json(
                    {
                        "type": "tool_result",
                        "toolCallId": "tc1",
                        "success": True,
                        "content": "ok",
                        "idempotencyKey": "k1",
                    }
                )
                # Poll for the port record; bail out if it never lands.
                for _ in range(50):
                    if port.calls:
                        return
                    await asyncio.sleep(0.02)

    asyncio.run(_drive())
    assert port.calls == [(run_id, "tc1", "ok", "k1")]
