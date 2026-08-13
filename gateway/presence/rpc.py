"""Request/response over a Presence channel. Does not know PTY or Sandbox."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from gateway.presence.channel import PresenceChannel
from gateway.presence.wire import EXEC_CALL, EXEC_RESULT


class ExecHub:
    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}

    async def call(
        self,
        channel: PresenceChannel,
        op: str,
        payload: dict[str, Any],
        *,
        timeout_s: float,
    ) -> dict[str, Any]:
        call_id = uuid4().hex[:12]
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[call_id] = fut
        try:
            await channel.send(
                {"type": EXEC_CALL, "call_id": call_id, "op": op, "payload": payload}
            )
            return await asyncio.wait_for(fut, timeout=timeout_s)
        finally:
            self._pending.pop(call_id, None)

    def complete(self, message: dict[str, Any]) -> None:
        if message.get("type") != EXEC_RESULT:
            return
        call_id = str(message.get("call_id") or "")
        fut = self._pending.get(call_id)
        if fut is None or fut.done():
            return
        fut.set_result(message)

    def fail_all(self, error: str) -> None:
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(ConnectionError(error))
        self._pending.clear()
