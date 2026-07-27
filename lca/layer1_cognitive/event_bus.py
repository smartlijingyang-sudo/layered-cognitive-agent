"""SimpleEventBus —— 异步事件广播。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from lca.contracts.protocols import EventBus


class SimpleEventBus(EventBus):
    """基于字典的简单事件总线。"""

    def __init__(self) -> None:
        self._subs: dict[str, list[Callable[[Any], Awaitable[None]]]] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def emit(self, event_name: str, payload: Any, trace_id: str) -> None:
        event_payload = {
            "event_name": event_name,
            "payload": payload,
            "trace_id": trace_id,
        }
        for handler in self._subs.get(event_name, []):
            task = asyncio.create_task(self._invoke(handler, event_payload))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _invoke(
        self, handler: Callable[[Any], Awaitable[None]], payload: dict[str, Any]
    ) -> None:
        await handler(payload)

    def subscribe(self, event_name: str, handler: Callable[[Any], Awaitable[None]]) -> None:
        self._subs.setdefault(event_name, []).append(handler)
