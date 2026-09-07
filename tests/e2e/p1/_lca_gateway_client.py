"""Python wire harness mirroring the TS ``lcaGateway/*.ts`` modules.

This harness is byte-compat with the wire protocol implemented by the
``LcaAgentGateway`` server (Task 8). It is used by the L3 e2e tests to
drive a real LCA kernel subprocess through the same HTTP + WebSocket
sequence the patched ``lcaGateway/*`` TS would.

Public API:

- :meth:`LcaGatewayClient.start_run` — mirrors ``lcaStartRun``
  (execute.ts).
- :meth:`LcaGatewayClient.get_running_operation` — mirrors
  ``lcaReconnectToGatewayOperation`` (reconnect.ts).
- :meth:`LcaGatewayClient.refresh_ws_token` — mirrors
  ``lcaRefreshWsToken`` (reconnect.ts).
- :meth:`LcaGatewayClient.connect_ws` / :meth:`resume` /
  :meth:`send_heartbeat` / :meth:`send_interrupt` /
  :meth:`send_tool_result` — mirror the AgentStreamClient control
  frames.
- :meth:`LcaGatewayClient.collect_events` — drains WS frames until
  the deadline.

The parity test (test_lca_p1_wire_harness_parity.py) compares this
harness's output to a Node script that ``require``s the actual TS;
any drift is caught in CI before the patch is shipped.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx


class LcaGatewayClient:
    """Python mirror of lobehub-ui/.../lcaGateway/*."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str = "lca-local",
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=httpx.Timeout(timeout),
        )
        self._ws: Any = None
        self._heartbeat_task: asyncio.Task | None = None

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
        await self._http.aclose()

    # ── HTTP ────────────────────────────────────────────────────────

    async def start_run(
        self,
        *,
        agent_id: str,
        messages: list[dict],
        parent_message_id: str | None = None,
        resume_approval: dict | None = None,
        resume_tool_result: dict | None = None,
    ) -> dict:
        """POST /lca-api/runs; return the run receipt.

        Mirrors ``lcaStartRun`` (lcaGateway/execute.ts).
        """
        body: dict = {
            "agent": {"id": agent_id, "name": agent_id},
            "messages": messages,
        }
        if parent_message_id is not None:
            body["parent_message_id"] = parent_message_id
        if resume_approval is not None:
            body["resume_approval"] = resume_approval
        if resume_tool_result is not None:
            body["resume_tool_result"] = resume_tool_result
        resp = await self._http.post("/lca-api/runs", json=body)
        resp.raise_for_status()
        return resp.json()

    async def get_running_operation(self, topic_id: str) -> dict | None:
        """GET /lca-api/topics/{topic_id}/running-op.

        Mirrors ``lcaReconnectToGatewayOperation`` (reconnect.ts).
        """
        resp = await self._http.get(f"/lca-api/topics/{topic_id}/running-op")
        resp.raise_for_status()
        body = resp.json()
        return body.get("running_operation")

    async def refresh_ws_token(self, run_id: str, user_id: str = "u1") -> str:
        """POST /lca-api/runs/{run_id}/ws-token.

        Mirrors ``lcaRefreshWsToken`` (reconnect.ts).
        """
        resp = await self._http.post(
            f"/lca-api/runs/{run_id}/ws-token", json={"userId": user_id}
        )
        resp.raise_for_status()
        return resp.json()["token"]

    # ── WebSocket ───────────────────────────────────────────────────

    async def connect_ws(self, run_id: str, token: str) -> None:
        """Open WS to /v1/runs/{run_id}/ws and complete the auth handshake.

        Mirrors ``AgentStreamClient.connect`` (agent-gateway-client) +
        the auth frame that LCA's gateway requires on top.
        """
        try:
            import websockets
        except ImportError as exc:  # pragma: no cover — fixture only
            raise RuntimeError(
                "the `websockets` package is required for connect_ws; "
                "add it to the dev extra in pyproject.toml"
            ) from exc

        ws_url = self._base_url.replace("http://", "ws://").replace(
            "https://", "wss://"
        )
        ws_url = f"{ws_url}/v1/runs/{run_id}/ws"
        self._ws = await websockets.connect(ws_url)
        await self._ws.send(json.dumps({"type": "auth", "token": token}))
        first = json.loads(await self._ws.recv())
        if first.get("type") != "auth_success":
            raise RuntimeError(f"auth failed: {first!r}")
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def resume(self, last_event_id: str, *, want_status: bool = True) -> None:
        """Send a `resume` control frame.

        Mirrors the AgentStreamClient resume handshake.
        """
        if self._ws is None:
            raise RuntimeError("connect_ws() must be called first")
        await self._ws.send(
            json.dumps(
                {
                    "type": "resume",
                    "lastEventId": last_event_id,
                    "wantStatus": want_status,
                }
            )
        )

    async def send_heartbeat(self) -> None:
        if self._ws is None:
            raise RuntimeError("connect_ws() must be called first")
        await self._ws.send(json.dumps({"type": "heartbeat"}))

    async def send_interrupt(self) -> None:
        if self._ws is None:
            raise RuntimeError("connect_ws() must be called first")
        await self._ws.send(json.dumps({"type": "interrupt"}))

    async def send_tool_result(
        self,
        *,
        tool_call_id: str,
        success: bool,
        content: str,
        idempotency_key: str,
    ) -> None:
        if self._ws is None:
            raise RuntimeError("connect_ws() must be called first")
        await self._ws.send(
            json.dumps(
                {
                    "type": "tool_result",
                    "toolCallId": tool_call_id,
                    "success": success,
                    "content": content,
                    "idempotencyKey": idempotency_key,
                }
            )
        )

    # ── Event collection ────────────────────────────────────────────

    async def collect_events(
        self, *, timeout: float = 5.0, max_events: int = 1000
    ) -> list[dict]:
        """Block until ``max_events`` events arrive or ``timeout`` elapses.

        Returns ``agent_event`` payloads AND any control frames
        (``auth_success``, ``auth_failed``, ``auth_expired``,
        ``heartbeat_ack``, ``resume_complete``, ``session_complete``).
        """
        if self._ws is None:
            raise RuntimeError("connect_ws() must be called first")
        out: list[dict] = []
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        while len(out) < max_events:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            frame = json.loads(raw)
            if frame.get("type") == "agent_event":
                out.append(frame["event"])
            else:
                out.append(frame)
        return out

    async def _heartbeat_loop(self) -> None:
        """Mirror native AgentStreamClient 30 s heartbeat."""
        while True:
            try:
                await asyncio.sleep(30.0)
                await self.send_heartbeat()
            except asyncio.CancelledError:
                return
            except Exception:
                return


__all__ = ("LcaGatewayClient",)