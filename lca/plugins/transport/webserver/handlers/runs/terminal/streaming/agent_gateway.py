"""LcaAgentGateway — Starlette WebSocketRoute for the agent runtime event bus.

Implements the same wire protocol as the upstream
`https://agent-gateway.lobehub.com` (the `ServerMessage` /
`ClientMessage` schemas from `lobehub-ui/packages/agent-gateway-client/src/types.ts:257-369`).
The front-end uses the unaltered `AgentStreamClient` package.

Wire behaviour:
- accept WS → expect first frame `{type:'auth', token}` → verify JWT
  → on success: send `{type:'auth_success'}`; on failure: `{type:'auth_failed'}` and close.
- expect next frame `{type:'resume', lastEventId, wantStatus?}` →
  read history (XREAD from `lastEventId`) → emit each as `agent_event`
  → if `wantStatus`: emit `resume_complete { status }` and close if terminal.
- after resume: subscribe to live stream (XREAD BLOCK 500) → emit each new event.
- 30s heartbeat: client sends `{type:'heartbeat'}` → server replies `{type:'heartbeat_ack'}`.
- `{type:'interrupt'}` → call `RunPort.cancel(run_id)`, close.
- `{type:'tool_result'}` → call `RunPort.resume_approval(...)`, continue.

After the run's `agent_runtime_end` is published, the server emits
`{type:'session_complete'}` and closes the socket.

Live-loop design (Task 7):
The subscribe generator is a long-running XREAD BLOCK consumer. We
cannot `await` it and `ws.receive_text` at the same time, so we
pump it into an `asyncio.Queue` via a background task and race
queue-drain against `ws.receive_text` with `asyncio.wait(..., return_when=FIRST_COMPLETED)`.
A short timeout (0.5s) bounds each iteration so a stale `recv`
future cannot wedge the loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any, Protocol, cast

from starlette.applications import Starlette
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from lca.infrastructure.observability.stream import (
    LcaStreamEventManager,
    get_agent_runtime_redis_client,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import (
    InvalidTokenError,
    verify_user_jwt,
)


class RunPort(Protocol):
    async def cancel(self, run_id: str) -> Any: ...

    async def resume_approval(
        self,
        run_id: str,
        approval_id: str,
        payload: str,
        idempotency_key: str,
    ) -> Any: ...


_HEARTBEAT_INTERVAL_S = 30.0
_RACE_TIMEOUT_S = 0.5
_PUMP_QUEUE_MAX = 256


def build_agent_gateway_app(*, run_port: RunPort | None = None) -> Starlette:
    """Build the Starlette app exposing /v1/runs/{run_id}/ws.

    The `run_port` parameter is optional; tests inject a fake; production
    passes the real LCA RunPort (resolved from app.state).
    """
    stream_manager = LcaStreamEventManager(get_agent_runtime_redis_client())

    async def handler(websocket: WebSocket) -> None:
        run_id = websocket.path_params.get("run_id")
        await websocket.accept()
        jwt_keys = getattr(websocket.app.state, "jwt_keys", None)
        public_pem = getattr(jwt_keys, "public_pem", None) if jwt_keys is not None else None
        try:
            await _run_session(
                websocket,
                run_id=run_id,
                stream_manager=stream_manager,
                run_port=run_port,
                public_pem=public_pem,
            )
        except WebSocketDisconnect:
            return
        except Exception as exc:
            print(f"[lca_agent_gateway] unhandled: {exc!r}", flush=True)
        finally:
            if websocket.client_state != WebSocketState.DISCONNECTED:
                try:
                    await websocket.close()
                except Exception:
                    pass

    return Starlette(routes=[WebSocketRoute("/v1/runs/{run_id}/ws", handler)])


async def _run_session(
    ws: WebSocket,
    *,
    run_id: str | None,
    stream_manager: LcaStreamEventManager,
    run_port: RunPort | None,
    public_pem: str | None = None,
) -> None:
    # 1. auth handshake
    try:
        first = await _recv_json(ws)
    except WebSocketDisconnect:
        return
    if not first or first.get("type") != "auth":
        await ws.send_json({"type": "auth_failed", "reason": "expected auth frame"})
        return
    token = first.get("token", "")
    try:
        verify_user_jwt(token, expected_operation_id=run_id, public_key_pem=public_pem)
    except InvalidTokenError as exc:
        await ws.send_json({"type": "auth_failed", "reason": str(exc)})
        return
    await ws.send_json({"type": "auth_success"})

    # 2. resume handshake (optional but expected)
    try:
        resume = await _recv_json(ws)
    except WebSocketDisconnect:
        return
    if not resume or resume.get("type") != "resume":
        last_id = "0"
        want_status = False
    else:
        last_id = resume.get("lastEventId", "0")
        want_status = resume.get("wantStatus", False)

    if run_id is not None:
        history = await stream_manager.read_history(run_id, count=1000)
        terminal_status = _terminal_status_from_history(history)
        history.reverse()
        for ev in history:
            if ev.get("id") and last_id != "0" and ev["id"] <= last_id:
                continue
            await _send_agent_event(ws, ev)
        if want_status:
            if terminal_status is not None:
                status = terminal_status
            else:
                status = "running" if await stream_manager.exists(run_id) else "completed"
            await ws.send_json({"type": "resume_complete", "status": status})
            if status in ("completed", "error", "interrupted"):
                await ws.send_json({"type": "session_complete"})
                return

    # 3. live loop: race XREAD stream pump vs incoming WS control frames
    if run_id is None:
        return
    await _live_loop(ws, run_id=run_id, stream_manager=stream_manager, run_port=run_port)


async def _live_loop(
    ws: WebSocket,
    *,
    run_id: str,
    stream_manager: LcaStreamEventManager,
    run_port: RunPort | None,
) -> None:
    """Race stream frames against client control frames until disconnect."""
    frame_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=_PUMP_QUEUE_MAX)
    pump_stop = asyncio.Event()
    last_id = "0"
    pump_task: asyncio.Task[None] | None = None
    pump_started = False

    async def _pump() -> None:
        try:
            async for frame in stream_manager.subscribe(run_id, last_id):
                if pump_stop.is_set():
                    return
                await frame_queue.put(frame)
        except Exception:
            pass

    async def _drain_queue() -> list[bytes]:
        frames: list[bytes] = []
        while not frame_queue.empty():
            try:
                frames.append(frame_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return frames

    try:
        while True:
            if ws.client_state == WebSocketState.DISCONNECTED:
                return

            if not pump_started:
                pump_task = asyncio.create_task(_pump())
                pump_started = True

            recv_task = asyncio.create_task(_recv_json(ws))
            try:
                done, _ = await asyncio.wait(
                    {recv_task},
                    timeout=_RACE_TIMEOUT_S,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            except Exception:
                recv_task.cancel()
                continue

            # 1. Forward any frames the pump queued during the wait window.
            queued = await _drain_queue()
            for frame in queued:
                if ws.client_state == WebSocketState.DISCONNECTED:
                    return
                try:
                    ev = _parse_sse_agent_event_frame(frame)
                    if ev is None:
                        continue
                    if await _forward_stream_event(ws, ev):
                        return
                except (WebSocketDisconnect, RuntimeError):
                    return
                next_id = ev.get("id") if ev is not None else None
                if next_id:
                    last_id = str(next_id)

            # 2. If a control frame arrived, handle it.
            if recv_task in done:
                # Attach a no-op done callback so a raised WebSocketDisconnect
                # (e.g. after we returned for "interrupt") is not flagged as
                # an unretrieved task exception in pytest logs.
                recv_task.add_done_callback(lambda _t: None)
                try:
                    msg = recv_task.result()
                except WebSocketDisconnect:
                    return
                except Exception:
                    msg = None
                if msg is not None:
                    handled = await _handle_control_frame(
                        ws, msg=msg, run_id=run_id, run_port=run_port
                    )
                    if handled == "interrupt":
                        return
                continue

            # 3. Otherwise the wait timed out; loop to keep draining the queue.
            recv_task.add_done_callback(lambda _t: None)
            recv_task.cancel()
            try:
                await recv_task
            except (asyncio.CancelledError, WebSocketDisconnect, Exception):
                pass
    finally:
        pump_stop.set()
        if pump_task is not None and not pump_task.done():
            pump_task.cancel()
            try:
                await pump_task
            except (asyncio.CancelledError, Exception):
                pass


async def _handle_control_frame(
    ws: WebSocket,
    *,
    msg: dict,
    run_id: str,
    run_port: RunPort | None,
) -> str:
    """Apply a client control frame. Return "interrupt" to close the loop."""
    mtype = msg.get("type")
    if mtype == "heartbeat":
        await ws.send_json({"type": "heartbeat_ack"})
        return "ok"
    if mtype == "interrupt":
        if run_port is not None:
            try:
                await run_port.cancel(run_id)
            except Exception:
                pass
        return "interrupt"
    if mtype == "tool_result":
        if run_port is not None:
            try:
                await run_port.resume_approval(
                    run_id,
                    msg.get("toolCallId", ""),
                    msg.get("content", ""),
                    msg.get("idempotencyKey", ""),
                )
            except Exception:
                pass
        return "ok"
    return "ok"


async def _recv_json(ws: WebSocket) -> dict | None:
    """Receive a JSON frame; tolerate SSE-shaped frames too."""
    payload = await ws.receive_text()
    if not payload:
        return None
    if payload.startswith(":"):
        return None
    for line in payload.split("\n"):
        if line.startswith("data:"):
            try:
                return cast("dict[str, Any]", json.loads(line[len("data:") :].strip()))
            except json.JSONDecodeError:
                continue
    try:
        return cast("dict[str, Any]", json.loads(payload))
    except json.JSONDecodeError:
        return None


async def _send_agent_event(ws: WebSocket, ev: dict) -> None:
    """Send a single AgentStreamEvent as a `agent_event` envelope."""
    envelope = {
        "type": "agent_event",
        "id": ev.get("id"),
        "event": {
            "type": ev.get("type"),
            "data": ev.get("data"),
            "operationId": ev.get("operationId"),
            "stepIndex": ev.get("stepIndex", 0),
            "timestamp": ev.get("timestamp", 0),
        },
    }
    await ws.send_json(envelope)


async def _forward_stream_event(ws: WebSocket, ev: dict) -> bool:
    """Forward one Redis stream row; return True when the run is terminal."""
    await _send_agent_event(ws, ev)
    if ev.get("type") != "agent_runtime_end":
        return False
    await ws.send_json({"type": "session_complete"})
    return True


def _terminal_status_from_history(history: list[dict]) -> str | None:
    """Map the newest terminal event in history to a resume_complete status."""
    for ev in history:
        if ev.get("type") != "agent_runtime_end":
            continue
        data = ev.get("data") or {}
        reason = str(data.get("reason") or "completed")
        final_state = data.get("finalState") or {}
        status = str(final_state.get("status") or reason)
        if status in {"completed", "done"}:
            return "completed"
        if status in {"error", "failed"}:
            return "error"
        if status in {"interrupted", "canceled", "cancelled"}:
            return "interrupted"
        if status in {"waiting_input", "waiting_for_human", "waiting_for_async_tool"}:
            return "waiting_input"
        return "completed"
    return None


def _parse_sse_agent_event_frame(frame: bytes) -> dict | None:
    """Decode one subscribe() SSE frame back into a Redis stream row."""
    try:
        text = frame.decode("utf-8")
    except UnicodeDecodeError:
        return None
    for line in text.split("\n"):
        if not line.startswith("data:"):
            continue
        try:
            envelope = json.loads(line[len("data:") :].strip())
        except json.JSONDecodeError:
            continue
        if envelope.get("type") != "agent_event":
            continue
        inner = envelope.get("event") or {}
        return {
            "id": envelope.get("id"),
            "type": inner.get("type"),
            "data": inner.get("data"),
            "operationId": inner.get("operationId"),
            "stepIndex": inner.get("stepIndex", 0),
            "timestamp": inner.get("timestamp", 0),
        }
    return None


def _extract_id_from_sse_frame(frame: bytes) -> str | None:
    """Parse an SSE-shaped frame for the `id:` line, return its value or None."""
    try:
        text = frame.decode("utf-8")
    except UnicodeDecodeError:
        return None
    for line in text.split("\n"):
        if line.startswith("id:"):
            return line[len("id:") :].strip() or None
    return None


def make_production_ws_handler() -> Any:
    """Return a WebSocket handler that resolves ``run_port`` from ``app.state``."""

    stream_manager = LcaStreamEventManager(get_agent_runtime_redis_client())

    async def handler(websocket: WebSocket) -> None:
        run_id = websocket.path_params.get("run_id")
        run_port: RunPort | None = getattr(websocket.app.state, "run_port", None)
        jwt_keys = getattr(websocket.app.state, "jwt_keys", None)
        public_pem = getattr(jwt_keys, "public_pem", None) if jwt_keys is not None else None
        await websocket.accept()
        try:
            await _run_session(
                websocket,
                run_id=run_id,
                stream_manager=stream_manager,
                run_port=run_port,
                public_pem=public_pem,
            )
        except WebSocketDisconnect:
            return
        except Exception as exc:
            print(f"[lca_agent_gateway] unhandled: {exc!r}", flush=True)
        finally:
            if websocket.client_state != WebSocketState.DISCONNECTED:
                with contextlib.suppress(Exception):
                    await websocket.close()

    return handler


__all__ = ("RunPort", "build_agent_gateway_app", "make_production_ws_handler")
