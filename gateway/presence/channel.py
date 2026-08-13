"""Outbound frame sink for one connected host. No Starlette types."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol


class PresenceChannel(Protocol):
    async def send(self, payload: dict[str, Any]) -> None: ...


Emit = Callable[[dict[str, Any]], Awaitable[None]]
