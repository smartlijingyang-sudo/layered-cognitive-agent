"""SimpleEventBus —— 异步事件广播。"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from contracts.protocols import EventBus


class SimpleEventBus(EventBus):
    """基于字典的简单事件总线。"""

    def __init__(self) -> None:
        self._subs: dict[str, list[Callable[[Any], Awaitable[None]]]] = {}

    def emit(self, event_name: str, payload: Any, trace_id: str) -> None:
        for handler in self._subs.get(event_name, []):
            asyncio.create_task(handler({"event_name": event_name, "payload": payload, "trace_id": trace_id}))

    def subscribe(self, event_name: str, handler: Callable[[Any], Awaitable[None]]) -> None:
        self._subs.setdefault(event_name, []).append(handler)
