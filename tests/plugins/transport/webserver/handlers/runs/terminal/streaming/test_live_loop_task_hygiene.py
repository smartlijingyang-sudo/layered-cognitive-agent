"""_live_loop task-hygiene regression tests (no real redis)."""

from __future__ import annotations

import asyncio
import gc
import json

from starlette.websockets import WebSocketDisconnect, WebSocketState

from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.agent_gateway import (
    _live_loop,
)


def _agent_event_frame(event_id: str = "1-0") -> bytes:
    envelope = {
        "type": "agent_event",
        "id": event_id,
        "event": {
            "type": "stream_chunk",
            "data": {"chunkType": "text", "content": "hi"},
            "operationId": "r1",
            "stepIndex": 0,
            "timestamp": 0,
        },
    }
    return f"id: {event_id}\nevent: agent_event\ndata: {json.dumps(envelope)}\n\n".encode()


class _DisconnectWS:
    client_state = WebSocketState.CONNECTED

    async def receive_text(self) -> str:
        # Let the pump enqueue first so the drain path runs before retrieve.
        await asyncio.sleep(0.1)
        raise WebSocketDisconnect(1000, "")

    async def send_json(self, _msg: dict) -> None:
        raise WebSocketDisconnect(1000, "")


class _DisconnectOnceSubscribe:
    async def subscribe(self, run_id: str, last_id: str):
        yield _agent_event_frame()
        # Hang until pump cancel; never swallow CancelledError so the
        # pump task can be cancelled cleanly without "Task was destroyed".
        await asyncio.Event().wait()


class _SilentWS:
    client_state = WebSocketState.CONNECTED

    async def receive_text(self) -> str:
        raise WebSocketDisconnect(1000, "")

    async def send_json(self, _msg: dict) -> None:
        return None


class _HangSubscribe:
    async def subscribe(self, run_id: str, last_id: str):
        await asyncio.Event().wait()
        if False:  # keep this an async generator without swallowing cancel
            yield b""


class _ScriptedWS:
    client_state = WebSocketState.CONNECTED

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self._texts = [
            '{"type":"heartbeat"}',
            '{"type":"tool_result","toolCallId":"t1","content":"ok","idempotencyKey":"k1"}',
        ]
        self._idx = 0

    async def receive_text(self) -> str:
        if self._idx < len(self._texts):
            text = self._texts[self._idx]
            self._idx += 1
            return text
        raise WebSocketDisconnect(1000, "")

    async def send_json(self, msg: dict) -> None:
        self.sent.append(msg)


class _RecordingPort:
    def __init__(self) -> None:
        self.resume_calls: list[tuple] = []

    async def cancel(self, run_id: str):
        return None

    async def resume_approval(
        self,
        run_id: str,
        approval_id: str,
        payload: str,
        idempotency_key: str,
        *,
        plugin_state=None,
        parent_message_id: str = "",
    ):
        self.resume_calls.append((run_id, approval_id, payload, idempotency_key))
        return None


async def test_queued_frame_plus_disconnect_leaves_no_orphan_task() -> None:
    loop = asyncio.get_running_loop()
    contexts: list[dict] = []
    old = loop.get_exception_handler()
    loop.set_exception_handler(lambda _l, ctx: contexts.append(ctx))
    try:
        await _live_loop(
            _DisconnectWS(),  # type: ignore[arg-type]
            run_id="r1",
            stream_manager=_DisconnectOnceSubscribe(),  # type: ignore[arg-type]
            run_port=None,
            start_id="",
        )
        gc.collect()
        # Yield once so a just-returned orphan task can reach __del__.
        await asyncio.sleep(0.1)
        gc.collect()
        await asyncio.sleep(0.1)
    finally:
        loop.set_exception_handler(old)
    orphans = [
        c
        for c in contexts
        if "never retrieved" in str(c.get("message", ""))
        and isinstance(c.get("exception"), WebSocketDisconnect)
    ]
    assert not orphans, f"orphan recv_task leaked: {orphans!r}"


async def test_clean_disconnect_while_waiting_returns_silently() -> None:
    loop = asyncio.get_running_loop()
    contexts: list[dict] = []
    old = loop.get_exception_handler()
    loop.set_exception_handler(lambda _l, ctx: contexts.append(ctx))
    try:
        await _live_loop(
            _SilentWS(),  # type: ignore[arg-type]
            run_id="r1",
            stream_manager=_HangSubscribe(),  # type: ignore[arg-type]
            run_port=None,
            start_id="",
        )
        gc.collect()
        # Same double-collect as the orphan test so both observe equal GC pressure.
        await asyncio.sleep(0)
        gc.collect()
    finally:
        loop.set_exception_handler(old)
    orphans = [
        c
        for c in contexts
        if "never retrieved" in str(c.get("message", ""))
        and isinstance(c.get("exception"), WebSocketDisconnect)
    ]
    assert not orphans, f"unexpected orphan task: {orphans!r}"


async def test_tool_result_and_heartbeat_dispatched() -> None:
    ws = _ScriptedWS()
    port = _RecordingPort()
    await _live_loop(
        ws,  # type: ignore[arg-type]
        run_id="r1",
        stream_manager=_HangSubscribe(),  # type: ignore[arg-type]
        run_port=port,  # type: ignore[arg-type]
        start_id="",
    )
    assert port.resume_calls == [("r1", "t1", "ok", "k1")]
    assert {"type": "heartbeat_ack"} in ws.sent
