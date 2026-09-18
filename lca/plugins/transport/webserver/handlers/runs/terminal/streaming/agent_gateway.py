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
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

from starlette.applications import Starlette
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from lca.infrastructure.observability.stream import (
    LcaStreamEventLog,
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
        *,
        plugin_state: dict[str, Any] | None = None,
        parent_message_id: str = "",
    ) -> Any: ...


_HEARTBEAT_INTERVAL_S = 30.0
_PUMP_QUEUE_MAX = 256


@dataclass(frozen=True, slots=True)
class _RecvMsg:
    msg: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class _RecvDisconnected:
    pass


@dataclass(frozen=True, slots=True)
class _RecvFailed:
    exc: Exception


RecvOutcome = _RecvMsg | _RecvDisconnected | _RecvFailed


@dataclass(frozen=True, slots=True)
class _LoopContinue:
    pass


@dataclass(frozen=True, slots=True)
class _LoopStop:
    reason: Literal["SilentDisconnect", "Terminal", "Interrupted"]


LoopVerdict = _LoopContinue | _LoopStop


def _classify_recv_task(task: asyncio.Task[dict[str, Any] | None]) -> RecvOutcome:
    """Map a finished recv task to Msg, silent disconnect, or swallowed failure."""
    try:
        return _RecvMsg(msg=task.result())
    except WebSocketDisconnect:
        return _RecvDisconnected()
    except asyncio.CancelledError:
        # Recv cancellation means the socket is gone; the client resumes from last_id.
        return _RecvDisconnected()
    except Exception as exc:
        return _RecvFailed(exc=exc)


async def _join_wait_tasks(*tasks: asyncio.Task[Any] | None) -> None:
    """Cancel pending wait tasks and retrieve finished ones."""
    # Retrieving every wait task keeps "never retrieved" warnings from escaping the loop.
    for task in tasks:
        if task is None:
            continue
        if not task.done():
            task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


def _dbg(msg: str, *args: Any) -> None:
    print(f"[LCA-DEBUG-WS] {msg}", *args, flush=True)


def build_agent_gateway_app(*, run_port: RunPort | None = None) -> Starlette:
    """Build the Starlette app exposing /v1/runs/{run_id}/ws.

    The `run_port` parameter is optional; tests inject a fake; production
    passes the real LCA RunPort (resolved from app.state).
    """
    stream_manager = LcaStreamEventLog(get_agent_runtime_redis_client())

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
    stream_manager: LcaStreamEventLog,
    run_port: RunPort | None,
    public_pem: str | None = None,
) -> None:
    _dbg("_run_session enter run_id=%s peer=%s", run_id, getattr(ws.client, "host", "?"))
    # 1. auth handshake
    try:
        first = await _recv_json(ws)
    except WebSocketDisconnect:
        _dbg("_run_session recv auth: disconnect run_id=%s", run_id)
        return
    except Exception as exc:
        _dbg("_run_session recv auth EXC run_id=%s: %r", run_id, exc)
        return
    _dbg(
        "_run_session recv auth frame: type=%s token_len=%s",
        (first or {}).get("type"),
        len((first or {}).get("token") or ""),
    )
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
    _dbg("sent auth_success run_id=%s", run_id)

    # 2. resume handshake (optional but expected)
    try:
        resume = await _recv_json(ws)
    except WebSocketDisconnect:
        _dbg("recv resume: WebSocketDisconnect run_id=%s", run_id)
        return
    except Exception as exc:
        _dbg("recv resume EXC run_id=%s: %r", run_id, exc)
        return
    _dbg(
        "recv resume frame: type=%s lastEventId=%s wantStatus=%s",
        (resume or {}).get("type"),
        (resume or {}).get("lastEventId"),
        (resume or {}).get("wantStatus"),
    )
    if not resume or resume.get("type") != "resume":
        last_id = "0"
        want_status = False
    else:
        last_id = resume.get("lastEventId", "0")
        want_status = resume.get("wantStatus", False)

    replayed_upto = "" if last_id == "0" else str(last_id)
    if run_id is not None:
        history = await stream_manager.read_history(run_id, count=1000)
        _dbg(
            "read_history run_id=%s count=%s replayed_upto=%s", run_id, len(history), replayed_upto
        )
        terminal_status = _terminal_status_from_history(history)
        history.reverse()
        sent = 0
        for ev in history:
            ev_id = str(ev.get("id") or "")
            if ev_id and replayed_upto and ev_id <= replayed_upto:
                continue
            await _send_agent_event(ws, ev)
            sent += 1
            if ev_id:
                replayed_upto = ev_id
        _dbg("replayed %s events run_id=%s", sent, run_id)
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
    await _live_loop(
        ws,
        run_id=run_id,
        stream_manager=stream_manager,
        run_port=run_port,
        start_id=replayed_upto,
    )


async def _live_loop(
    ws: WebSocket,
    *,
    run_id: str,
    stream_manager: LcaStreamEventLog,
    run_port: RunPort | None,
    start_id: str = "",
) -> None:
    """Wait on {frame_ready, recv} with a heartbeat sweep until the run ends.

    Only a newly queued stream frame or an arrived client control frame wakes the loop; a heartbeat-interval timeout re-waits without cancelling either task, starting the pump strictly after start_id so the replayed prefix is never redelivered.

    Drained stream frames forward before the control frame is handled, and every SilentDisconnect, Terminal, or Interrupted exit funnels through cancel-and-await of both wait tasks.
    """
    _dbg("_live_loop enter run_id=%s start_id=%s", run_id, start_id)
    frame_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=_PUMP_QUEUE_MAX)
    pump_stop = asyncio.Event()
    last_id = start_id or "0"
    pump_task: asyncio.Task[None] | None = None
    pump_started = False
    recv_task: asyncio.Task[dict[str, Any] | None] | None = None
    frame_task: asyncio.Task[bytes] | None = None

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

    async def _funnel(
        recv: asyncio.Task[dict[str, Any] | None] | None,
        frame_ready: asyncio.Task[bytes] | None,
    ) -> None:
        # Single exit path keeps GC silent: a finished recv holding disconnect must be retrieved, not dropped.
        await _join_wait_tasks(recv, frame_ready)

    try:
        recv_task = asyncio.create_task(_recv_json(ws))
        frame_task = asyncio.create_task(frame_queue.get())
        while True:
            if ws.client_state == WebSocketState.DISCONNECTED:
                await _funnel(recv_task, frame_task)
                return

            if not pump_started:
                pump_task = asyncio.create_task(_pump())
                pump_started = True

            done, _pending = await asyncio.wait(
                {recv_task, frame_task},
                timeout=_HEARTBEAT_INTERVAL_S,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                # Sweep timeout with both pending must not cancel: control frames on the boundary stay exactly-once.
                continue

            if frame_task in done:
                try:
                    first_frame = frame_task.result()
                except asyncio.CancelledError:
                    await _funnel(recv_task, frame_task)
                    return
                except Exception as exc:
                    # queue.get has no fallible path; recreating keeps the two-task wait set whole.
                    _dbg("frame_ready failed: %r", exc)
                    frame_task = asyncio.create_task(frame_queue.get())
                else:
                    rest = await _drain_queue()
                    frames = [first_frame, *rest]
                    verdict: LoopVerdict = _LoopContinue()
                    for frame in frames:
                        if ws.client_state == WebSocketState.DISCONNECTED:
                            verdict = _LoopStop(reason="SilentDisconnect")
                            break
                        try:
                            ev = _parse_sse_agent_event_frame(frame)
                            if ev is None:
                                continue
                            if await _forward_stream_event(ws, ev):
                                verdict = _LoopStop(reason="Terminal")
                                break
                        except (WebSocketDisconnect, RuntimeError):
                            # Send side is gone; the client resumes from last_id, so exit quietly.
                            verdict = _LoopStop(reason="SilentDisconnect")
                            break
                        next_id = ev.get("id")
                        if next_id:
                            last_id = str(next_id)
                    if isinstance(verdict, _LoopStop):
                        await _funnel(recv_task, frame_task)
                        return
                    # The consumed frame already sits in `frames`, so a fresh get() loses nothing.
                    frame_task = asyncio.create_task(frame_queue.get())

            if recv_task in done:
                outcome: RecvOutcome = _classify_recv_task(recv_task)
                if isinstance(outcome, _RecvDisconnected):
                    await _funnel(recv_task, frame_task)
                    return
                if isinstance(outcome, _RecvFailed):
                    # Unknown recv failure carries no control intent; keep waiting with a fresh recv.
                    _dbg("recv failed: %r", outcome.exc)
                    recv_task = asyncio.create_task(_recv_json(ws))
                    continue
                msg = outcome.msg
                if msg is None:
                    recv_task = asyncio.create_task(_recv_json(ws))
                    continue
                try:
                    handled = await _handle_control_frame(
                        ws, msg=msg, run_id=run_id, run_port=run_port
                    )
                except (WebSocketDisconnect, RuntimeError):
                    await _funnel(recv_task, frame_task)
                    return
                if handled == "interrupt":
                    await _funnel(recv_task, frame_task)
                    return
                recv_task = asyncio.create_task(_recv_json(ws))
    finally:
        pump_stop.set()
        if pump_task is not None and not pump_task.done():
            pump_task.cancel()
            try:
                await pump_task
            except (asyncio.CancelledError, Exception):
                pass
        await _join_wait_tasks(recv_task, frame_task)


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
    _dbg(
        "_send_agent_event id=%s type=%s",
        ev.get("id"),
        (ev.get("data") or {}).get("type") if isinstance(ev.get("data"), dict) else ev.get("type"),
    )
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

    stream_manager = LcaStreamEventLog(get_agent_runtime_redis_client())

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
