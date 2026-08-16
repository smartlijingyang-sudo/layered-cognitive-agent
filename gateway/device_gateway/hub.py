"""Correlate outbound device requests with inbound responses + DSH turn streams."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import structlog

from gateway.device_gateway.registry import DeviceRegistry
from lca.layer0_infra.dsh.models import DshNotification, DshTurnResult
from lca.layer0_infra.dsh.runtime import DshUnavailableError
from lca.layer0_infra.dsh.wire import (
    DSH_CANCEL_TURN,
    DSH_NOTIFICATION,
    DSH_RUN_TURN_REQUEST,
    DSH_TURN_FINISHED,
)

_log = structlog.get_logger(__name__)


@dataclass(slots=True)
class _DshTurnSession:
    device_id: str
    future: asyncio.Future[dict[str, Any]]
    on_notification: Callable[[DshNotification], None]


class DeviceHub:
    def __init__(self, registry: DeviceRegistry) -> None:
        self._registry = registry
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._dsh_sessions: dict[str, _DshTurnSession] = {}

    async def call_tool(
        self,
        device_id: str,
        tool_call: dict[str, Any],
        *,
        timeout_s: float,
    ) -> dict[str, Any]:
        request_id = uuid4().hex[:16]
        return await self._send(
            device_id,
            {
                "type": "tool_call_request",
                "requestId": request_id,
                "toolCall": tool_call,
                "timeout": int(timeout_s * 1000),
            },
            request_id,
            timeout_s=timeout_s,
        )

    async def call_rpc(
        self,
        device_id: str,
        method: str,
        params: Any,
        *,
        timeout_s: float,
    ) -> dict[str, Any]:
        request_id = uuid4().hex[:16]
        return await self._send(
            device_id,
            {
                "type": "rpc_request",
                "requestId": request_id,
                "method": method,
                "params": params,
                "timeout": int(timeout_s * 1000),
            },
            request_id,
            timeout_s=timeout_s,
        )

    async def run_dsh_turn(
        self,
        device_id: str,
        *,
        turn_id: str,
        params: dict[str, Any],
        on_notification: Callable[[DshNotification], None],
        timeout_s: float,
    ) -> DshTurnResult:
        """Start a DSH turn on ``device_id``; ``on_notification`` fires on gateway loop."""
        conn = self._registry.channel(device_id)
        if conn is None:
            raise ConnectionError(f"device {device_id} offline")
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._dsh_sessions[turn_id] = _DshTurnSession(
            device_id=device_id,
            future=fut,
            on_notification=on_notification,
        )
        try:
            await conn.websocket.send_json(
                {
                    "type": DSH_RUN_TURN_REQUEST,
                    "turnId": turn_id,
                    "params": params,
                    "timeout": int(timeout_s * 1000),
                }
            )
            raw = await asyncio.wait_for(fut, timeout=timeout_s)
        except TimeoutError as exc:
            await self._cancel_dsh_turn(device_id, turn_id)
            raise TimeoutError(f"DSH turn {turn_id} timed out after {timeout_s}s") from exc
        finally:
            self._dsh_sessions.pop(turn_id, None)
        if not raw.get("success", True):
            error = str(raw.get("error") or "DSH turn failed")
            raise DshUnavailableError(error)
        return DshTurnResult(
            session_id=str(raw.get("session_id") or turn_id),
            final_response=str(raw.get("final_response") or ""),
            finish_reason=raw.get("finish_reason"),
        )

    def relay_dsh_notification(self, turn_id: str, method: str, payload: dict[str, Any]) -> None:
        session = self._dsh_sessions.get(turn_id)
        if session is None:
            return
        try:
            session.on_notification(DshNotification(method=method, payload=payload))
        except Exception:
            _log.warning("dsh_notification_handler_failed", turn_id=turn_id, exc_info=True)

    def complete_dsh_turn(self, turn_id: str, result: dict[str, Any]) -> None:
        session = self._dsh_sessions.pop(turn_id, None)
        if session is None or session.future.done():
            return
        session.future.set_result(result)

    def fail_dsh_turn(self, turn_id: str, error: str) -> None:
        session = self._dsh_sessions.pop(turn_id, None)
        if session is None or session.future.done():
            return
        session.future.set_exception(DshUnavailableError(error))

    async def _cancel_dsh_turn(self, device_id: str, turn_id: str) -> None:
        conn = self._registry.channel(device_id)
        if conn is None:
            return
        try:
            await conn.websocket.send_json({"type": DSH_CANCEL_TURN, "turnId": turn_id})
        except Exception:
            _log.warning("dsh_cancel_send_failed", turn_id=turn_id, exc_info=True)

    def complete(self, request_id: str, result: dict[str, Any]) -> None:
        fut = self._pending.get(request_id)
        if fut is None or fut.done():
            return
        fut.set_result(result)

    def fail_device(self, device_id: str, error: str) -> None:
        for turn_id, session in list(self._dsh_sessions.items()):
            if session.device_id != device_id:
                continue
            if not session.future.done():
                session.future.set_exception(ConnectionError(error))
            self._dsh_sessions.pop(turn_id, None)
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(ConnectionError(error))
        self._pending.clear()

    def handle_dsh_inbound(self, msg: dict[str, Any]) -> None:
        kind = str(msg.get("type") or "")
        turn_id = str(msg.get("turnId") or "")
        if not turn_id:
            return
        if kind == DSH_NOTIFICATION:
            method = str(msg.get("method") or "")
            payload = msg.get("payload")
            body = payload if isinstance(payload, dict) else {}
            self.relay_dsh_notification(turn_id, method, body)
            return
        if kind == DSH_TURN_FINISHED:
            result = msg.get("result")
            body = result if isinstance(result, dict) else {}
            self.complete_dsh_turn(turn_id, body)
            return

    async def _send(
        self,
        device_id: str,
        message: dict[str, Any],
        request_id: str,
        *,
        timeout_s: float,
    ) -> dict[str, Any]:
        conn = self._registry.channel(device_id)
        if conn is None:
            raise ConnectionError(f"device {device_id} offline")
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[request_id] = fut
        try:
            await conn.websocket.send_json(message)
            return await asyncio.wait_for(fut, timeout=timeout_s)
        finally:
            self._pending.pop(request_id, None)


def encode_arguments(arguments: dict[str, Any] | str) -> str:
    if isinstance(arguments, str):
        return arguments
    return json.dumps(arguments, ensure_ascii=False)
