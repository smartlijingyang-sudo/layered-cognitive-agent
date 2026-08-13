"""Console book talks to Presence channel, never to Starlette."""

from __future__ import annotations

from typing import Any

import pytest

from gateway.console.sessions import ConsoleBook, DeviceOfflineError
from gateway.presence.models import Device
from gateway.presence.registry import PresenceRegistry
from gateway.presence.wire import PTY_INPUT, PTY_OPEN, PTY_OUTPUT


class _Sink:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_open_sends_pty_open() -> None:
    presence = PresenceRegistry()
    sink = _Sink()
    presence.online(Device(device_id="h1", subject="u", name="box"), sink)
    book = ConsoleBook()
    session = await book.open(presence, "h1", cols=100, rows=30)
    assert sink.sent[0]["type"] == PTY_OPEN
    assert sink.sent[0]["session_id"] == session.session_id
    assert sink.sent[0]["cols"] == 100
    await book.send_input(presence, session, "ls\n")
    assert sink.sent[1] == {
        "type": PTY_INPUT,
        "session_id": session.session_id,
        "data": "ls\n",
    }


@pytest.mark.asyncio
async def test_open_offline_raises() -> None:
    book = ConsoleBook()
    with pytest.raises(DeviceOfflineError):
        await book.open(PresenceRegistry(), "missing")


@pytest.mark.asyncio
async def test_ingest_reaches_session_queue() -> None:
    presence = PresenceRegistry()
    presence.online(Device(device_id="h1", subject="u", name="box"), _Sink())
    book = ConsoleBook()
    session = await book.open(presence, "h1")
    book.ingest({"type": PTY_OUTPUT, "session_id": session.session_id, "data": "hi"})
    item = await session.output.get()
    assert item is not None
    assert item["data"] == "hi"
