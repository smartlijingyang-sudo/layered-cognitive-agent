"""PTY session book. Translates Console attach <-> Presence channel frames."""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from gateway.presence.models import CAP_CONSOLE, DeviceStatus
from gateway.presence.registry import PresenceRegistry
from gateway.presence.wire import PTY_CLOSE, PTY_INPUT, PTY_OPEN, PTY_RESIZE


@dataclass(slots=True)
class ConsoleSession:
    session_id: str
    device_id: str
    created_at: float
    output: asyncio.Queue[dict[str, Any] | None] = field(default_factory=lambda: asyncio.Queue(256))


class ConsoleBook:
    def __init__(self) -> None:
        self._sessions: dict[str, ConsoleSession] = {}

    def get(self, session_id: str) -> ConsoleSession | None:
        return self._sessions.get(session_id)

    async def open(
        self,
        presence: PresenceRegistry,
        device_id: str,
        *,
        cols: int = 80,
        rows: int = 24,
    ) -> ConsoleSession:
        device = presence.get(device_id)
        if device is None or device.status is not DeviceStatus.ONLINE:
            raise DeviceOfflineError(device_id)
        if CAP_CONSOLE not in device.capabilities:
            raise CapabilityMissingError(device_id, CAP_CONSOLE)
        channel = presence.channel(device_id)
        if channel is None:
            raise DeviceOfflineError(device_id)
        session = ConsoleSession(
            session_id=uuid4().hex[:12],
            device_id=device_id,
            created_at=time.time(),
        )
        self._sessions[session.session_id] = session
        await channel.send(
            {
                "type": PTY_OPEN,
                "session_id": session.session_id,
                "cols": cols,
                "rows": rows,
            }
        )
        return session

    async def send_input(
        self, presence: PresenceRegistry, session: ConsoleSession, data: str
    ) -> None:
        channel = presence.channel(session.device_id)
        if channel is None:
            raise DeviceOfflineError(session.device_id)
        await channel.send({"type": PTY_INPUT, "session_id": session.session_id, "data": data})

    async def resize(
        self,
        presence: PresenceRegistry,
        session: ConsoleSession,
        cols: int,
        rows: int,
    ) -> None:
        channel = presence.channel(session.device_id)
        if channel is None:
            return
        await channel.send(
            {
                "type": PTY_RESIZE,
                "session_id": session.session_id,
                "cols": cols,
                "rows": rows,
            }
        )

    async def close(self, presence: PresenceRegistry, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session is None:
            return
        self._end_queue(session)
        channel = presence.channel(session.device_id)
        if channel is None:
            return
        await channel.send({"type": PTY_CLOSE, "session_id": session_id})

    def ingest(self, payload: dict[str, Any]) -> None:
        session_id = str(payload.get("session_id") or "")
        session = self._sessions.get(session_id)
        if session is None:
            return
        try:
            session.output.put_nowait(payload)
        except asyncio.QueueFull:
            self._end_queue(session)

    def close_device(self, device_id: str) -> None:
        for session_id, session in list(self._sessions.items()):
            if session.device_id == device_id:
                self._sessions.pop(session_id, None)
                self._end_queue(session)

    def _end_queue(self, session: ConsoleSession) -> None:
        with contextlib.suppress(asyncio.QueueFull):
            session.output.put_nowait(None)


class DeviceOfflineError(Exception):
    def __init__(self, device_id: str) -> None:
        super().__init__(device_id)
        self.device_id = device_id


class CapabilityMissingError(Exception):
    def __init__(self, device_id: str, capability: str) -> None:
        super().__init__(f"{device_id} lacks {capability}")
        self.device_id = device_id
        self.capability = capability
