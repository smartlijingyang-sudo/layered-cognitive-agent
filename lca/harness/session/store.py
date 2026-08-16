"""SessionStore — append-only session journal wrapping optional RunStore."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from lca.contracts.harness.session import (
    EventScope,
    SessionEvent,
    SessionHeader,
    event_type_of,
)
from lca.harness.session.persistence import JsonlSessionPersistence

EventListener = Callable[[SessionEvent], None]


class SessionStore:
    """Append-only session fact log.

    Wraps optional JSONL persistence. Seq is allocated under an asyncio lock
    so concurrent commands cannot open a gap (spec §6.8).
    """

    def __init__(
        self,
        header: SessionHeader,
        *,
        persistence: JsonlSessionPersistence | None = None,
        events: list[SessionEvent] | None = None,
    ) -> None:
        self._header = header
        self._persistence = persistence
        self._events: list[SessionEvent] = list(events or [])
        self._seq = self._events[-1].seq if self._events else -1
        self._seq_lock = asyncio.Lock()
        self._listeners: list[EventListener] = []
        if self._persistence is not None:
            self._persistence.write_header(header)

    @property
    def header(self) -> SessionHeader:
        return self._header

    @property
    def current_seq(self) -> int:
        return self._seq

    def subscribe(self, listener: EventListener) -> None:
        self._listeners.append(listener)

    async def append(
        self,
        event_data: Any,
        *,
        actor: str | None = None,
        causation_id: str | None = None,
        visibility: str | None = None,
    ) -> SessionEvent:
        type_name = event_type_of(event_data)
        vis = visibility or getattr(type(event_data), "_visibility", "model")
        async with self._seq_lock:
            self._seq += 1
            seq = self._seq
        event = SessionEvent(
            type=type_name,
            seq=seq,
            time=int(time.time() * 1000),
            data=asdict(event_data),
            session_id=self._header.id,
            actor=actor,
            visibility=vis,  # type: ignore[arg-type]
            scope=EventScope(causation_id=causation_id, scope_id=self._header.id),
        )
        self._events.append(event)
        if self._persistence is not None:
            self._persistence.write_event(event)
        for listener in self._listeners:
            listener(event)
        return event

    async def read_from(self, seq: int = 0) -> list[SessionEvent]:
        return [event for event in self._events if event.seq >= seq]

    def events(self) -> tuple[SessionEvent, ...]:
        return tuple(self._events)

    @classmethod
    def load(cls, persistence: JsonlSessionPersistence) -> SessionStore:
        header, events = persistence.load()
        if header is None:
            raise FileNotFoundError(f"no session header in {persistence.path}")
        return cls(header, persistence=persistence, events=events)
