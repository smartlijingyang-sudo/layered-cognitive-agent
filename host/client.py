"""Presence client: hello, then dispatch PTY frames to LocalPty."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from gateway.presence.wire import (
    EXEC_CALL,
    EXEC_RESULT,
    HELLO,
    PTY_CLOSE,
    PTY_INPUT,
    PTY_OPEN,
    PTY_RESIZE,
    WELCOME,
)
from host.exec import handle_exec
from host.pty import LocalPty
from host.settings import HostSettings

_log = structlog.get_logger(__name__)


async def run_forever(settings: HostSettings) -> None:
    while True:
        try:
            await run_once(settings)
        except asyncio.CancelledError:
            raise
        except Exception:
            _log.warning("host_disconnected", exc_info=True)
        await asyncio.sleep(settings.reconnect_s)


async def run_once(settings: HostSettings) -> None:
    import websockets

    async with websockets.connect(settings.gateway) as ws:
        await ws.send(
            _json(
                {
                    "type": HELLO,
                    "device_id": settings.device_id,
                    "token": settings.token,
                    "name": settings.display_name(),
                    "capabilities": ["console", "sandbox"],
                }
            )
        )
        raw = await ws.recv()
        welcome = _parse(raw)
        if welcome.get("type") != WELCOME:
            raise RuntimeError(f"expected welcome, got {welcome!r}")
        _log.info("host_connected", device_id=settings.device_id, gateway=settings.gateway)
        ptys: dict[str, LocalPty] = {}

        async def emit(payload: dict[str, Any]) -> None:
            await ws.send(_json(payload))

        try:
            async for raw in ws:
                msg = _parse(raw)
                kind = msg.get("type")
                session_id = str(msg.get("session_id") or "")
                if kind == PTY_OPEN:
                    existing = ptys.pop(session_id, None)
                    if existing is not None:
                        existing.close()
                    session = LocalPty(
                        session_id,
                        emit,
                        settings.shell_argv(),
                        cols=int(msg.get("cols") or 80),
                        rows=int(msg.get("rows") or 24),
                    )
                    ptys[session_id] = session
                    await session.start()
                elif kind == PTY_INPUT:
                    pty = ptys.get(session_id)
                    if pty is not None:
                        pty.write(str(msg.get("data") or ""))
                elif kind == PTY_RESIZE:
                    pty = ptys.get(session_id)
                    if pty is not None:
                        pty.resize(int(msg.get("cols") or 80), int(msg.get("rows") or 24))
                elif kind == PTY_CLOSE:
                    pty = ptys.pop(session_id, None)
                    if pty is not None:
                        pty.close()
                elif kind == EXEC_CALL:
                    try:
                        result = await handle_exec(
                            str(msg.get("op") or ""),
                            msg.get("payload") if isinstance(msg.get("payload"), dict) else {},
                            settings.workspace(),
                        )
                        ok = bool(result.get("success", False))
                    except (OSError, ValueError, TypeError) as exc:
                        _log.warning("host_exec_failed", error=str(exc))
                        result = {
                            "success": False,
                            "exit_code": 1,
                            "error": str(exc),
                            "stderr": str(exc) + "\n",
                        }
                        ok = False
                    await emit(
                        {
                            "type": EXEC_RESULT,
                            "call_id": msg.get("call_id"),
                            "ok": ok,
                            "result": result,
                        }
                    )
        finally:
            for pty in ptys.values():
                pty.close()


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _parse(raw: str | bytes) -> dict[str, Any]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}
