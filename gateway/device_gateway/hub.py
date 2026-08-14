"""Correlate outbound device requests with inbound responses."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

from gateway.device_gateway.registry import DeviceRegistry


class DeviceHub:
    def __init__(self, registry: DeviceRegistry) -> None:
        self._registry = registry
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}

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

    def complete(self, request_id: str, result: dict[str, Any]) -> None:
        fut = self._pending.get(request_id)
        if fut is None or fut.done():
            return
        fut.set_result(result)

    def fail_device(self, device_id: str, error: str) -> None:
        del device_id
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(ConnectionError(error))
        self._pending.clear()

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
