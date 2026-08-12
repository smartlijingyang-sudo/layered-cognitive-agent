"""Typed event bus — replaces string-based SSE frame broadcasting.

Before refactoring, events flowed through:
    Journal → SSEJournalProjector → emit(SSE text frame) → RunSession
    → OpenAISSEProjector.project_frame(frame) → parse JSON → restore event

Now events flow through:
    Journal → EventBusProjector → EventBus → RunSession
    → OpenAIStreamEmitter.consume(stamped) → chunks directly

No string serialization round-trip. Typed events all the way.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from lca.contracts.atoms.enums import StreamChannel
from lca.contracts.models.observability.journal import (
    RunInsight,
    StampedEvent,
    StepTextDelta,
)
from lca.contracts.protocols import JournalProjector

# ── EventBus ──────────────────────────────────────────────

_SENTINEL: StampedEvent | None = None
"""Queue close sentinel — mirrors SSEJournalProjector.close() contract."""

_MAX_BUFFERED = 4096
"""Maximum frames buffered per subscriber for disconnect-replay."""

_MAX_QUEUE = 256
"""Per-subscriber async queue capacity."""


@dataclass
class EventBus:
    """Typed pub/sub for journal events.

    Replaces the string-based ``RunSession.emit(frame)`` broadcast.
    Carries ``StampedEvent`` objects directly — consumers get typed
    journal events without parsing SSE text frames.
    """

    _subscribers: list[asyncio.Queue[StampedEvent | None]] = field(
        default_factory=list, init=False, repr=False
    )
    _frames: list[StampedEvent] = field(default_factory=list, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    @property
    def is_closed(self) -> bool:
        return self._closed

    def buffered_after(self, after_seq: int = 0) -> list[StampedEvent]:
        """Return buffered events with seq > after_seq (non-blocking snapshot)."""
        return [s for s in self._frames if s.seq > after_seq]

    def publish(self, stamped: StampedEvent) -> None:
        """Buffer event and broadcast to all live subscribers."""
        if self._closed:
            return
        if len(self._frames) >= _MAX_BUFFERED:
            self._frames.pop(0)
        self._frames.append(stamped)
        dead: list[asyncio.Queue[StampedEvent | None]] = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(stamped)
            except asyncio.QueueFull:
                dead.append(queue)
        for queue in dead:
            self._subscribers.remove(queue)

    def close(self) -> None:
        """Signal all subscribers that no more events will arrive."""
        if self._closed:
            return
        self._closed = True
        for queue in self._subscribers:
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(_SENTINEL)
        self._subscribers.clear()

    def subscribe(self, after_seq: int = 0) -> AsyncIterator[StampedEvent]:
        """Replay buffered events (seq > after_seq), then stream live.

        Supports disconnect-recovery: pass the last ``seq`` the client
        received to skip already-delivered events.
        """
        return self._subscribe_impl(after_seq)

    async def _subscribe_impl(self, after_seq: int) -> AsyncIterator[StampedEvent]:
        # Replay buffered frames past the client's last seen seq
        for stamped in self._frames:
            if stamped.seq > after_seq:
                yield stamped
        if self._closed:
            return
        # Subscribe to live events
        queue: asyncio.Queue[StampedEvent | None] = asyncio.Queue(maxsize=_MAX_QUEUE)
        self._subscribers.append(queue)
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)


# ── EventBusProjector ─────────────────────────────────────


class EventBusProjector(JournalProjector):
    """Journal projector that forwards typed events to an ``EventBus``.

    Filters:
    - ``RunInsight`` — non-critical, InsightEngine feedback loop
    - ``StepTextDelta(channel=decision)`` — internal reasoning channel,
      only answer-channel text goes to the frontend

    Replaces ``SSEJournalProjector`` for the HTTP streaming path.
    Unlike ``SSEJournalProjector``, this projector never serializes
    events to strings — the typed ``StampedEvent`` flows through as-is.
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    def on_event(self, stamped: StampedEvent) -> None:
        if isinstance(stamped.event, RunInsight):
            return
        if (
            isinstance(stamped.event, StepTextDelta)
            and stamped.event.channel == StreamChannel.DECISION.value
        ):
            return
        self._bus.publish(stamped)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self._bus.close()
