"""LiveTail — Journal projector for in-process live subscribers.

One book, two readers: jsonl on disk, this tail on the socket.
Not a bus, not a protocol, not a filter.
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass

import structlog

from lca.contracts.models.observability.journal import StampedEvent, StepTextDelta
from lca.contracts.observability.run_journal import LiveRunProjection
from lca.contracts.protocols import JournalProjector
from lca.infrastructure.observability.journal.sse.frames import stamped_to_sse_frame

_log = structlog.get_logger(__name__)

_MAX_BUFFERED: int = 4096
_MAX_QUEUE: int = 256
_OVERFLOW_THRESHOLD: int = 3
_HEARTBEAT_INTERVAL_S: float = 15.0
_HEARTBEAT = b": keepalive\n\n"
TEXT_CHANNEL_ALL: str = "all"
TEXT_CHANNEL_ANSWER: str = "answer"


@dataclass(frozen=True, slots=True)
class LiveGap:
    """Transport control signal: requested seq was evicted from the ring.

    Not a Journal event. Must not be written to jsonl.
    """

    requested_seq: int
    oldest_seq: int


@dataclass(slots=True)
class _Subscriber:
    queue: asyncio.Queue[StampedEvent | None]
    overflow_count: int = 0


class LiveTail(JournalProjector):
    """Ring buffer + pub/sub + replay. Speaks only StampedEvent."""

    __slots__ = (
        "_closed",
        "_evicted",
        "_frames",
        "_last_seq",
        "_subscribers",
    )

    def __init__(self) -> None:
        self._frames: deque[StampedEvent] = deque(maxlen=_MAX_BUFFERED)
        self._subscribers: list[_Subscriber] = []
        self._closed: bool = False
        self._evicted: int = 0
        self._last_seq: int = 0

    @property
    def buffer_capacity(self) -> int:
        return _MAX_BUFFERED

    @property
    def queue_capacity(self) -> int:
        return _MAX_QUEUE

    @property
    def overflow_threshold(self) -> int:
        return _OVERFLOW_THRESHOLD

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    @property
    def buffer_size(self) -> int:
        return len(self._frames)

    @property
    def last_seq(self) -> int:
        return self._last_seq

    @property
    def evicted(self) -> int:
        return self._evicted

    def on_event(self, stamped: StampedEvent) -> None:
        if self._closed:
            return
        self._frames.append(stamped)
        self._last_seq = max(self._last_seq, stamped.seq)
        dead: list[int] = []
        for idx, sub in enumerate(self._subscribers):
            try:
                sub.queue.put_nowait(stamped)
                sub.overflow_count = 0
            except asyncio.QueueFull:
                sub.overflow_count += 1
                if sub.overflow_count >= _OVERFLOW_THRESHOLD:
                    dead.append(idx)
                    self._evicted += 1
                    _log.error(
                        "live_tail_subscriber_evicted",
                        hop="H3",
                        consecutive_overflows=sub.overflow_count,
                        queue_size=_MAX_QUEUE,
                        seq=stamped.seq,
                    )
                else:
                    _log.warning(
                        "live_tail_overflow",
                        hop="H3",
                        overflow_count=sub.overflow_count,
                        queue_utilization=sub.queue.qsize() / _MAX_QUEUE,
                        threshold=_OVERFLOW_THRESHOLD,
                        queue_size=_MAX_QUEUE,
                        seq=stamped.seq,
                    )
        for idx in reversed(dead):
            self._subscribers.pop(idx)

    def flush(self) -> None:
        return None

    async def subscribe(self, after_seq: int = 0) -> AsyncIterator[StampedEvent | LiveGap]:
        """Register first, then replay, then live — no drop window."""
        queue: asyncio.Queue[StampedEvent | None] = asyncio.Queue(_MAX_QUEUE)
        sub = _Subscriber(queue=queue)
        self._subscribers.append(sub)

        oldest_seq = self._frames[0].seq if self._frames else None
        # after_seq=0 means "from the start". A gap exists only when the ring
        # dropped something the subscriber asked for (oldest > after_seq + 1).
        if oldest_seq is not None and oldest_seq > after_seq + 1:
            yield LiveGap(requested_seq=after_seq, oldest_seq=oldest_seq)

        replay_count = 0
        for stamped in self._frames:
            if stamped.seq > after_seq:
                yield stamped
                replay_count += 1
                if replay_count % 64 == 0:
                    await asyncio.sleep(0)

        if self._closed:
            self._drop(queue)
            return

        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if item.seq > after_seq:
                    yield item
        finally:
            self._drop(queue)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for sub in self._subscribers:
            try:
                sub.queue.put_nowait(None)
            except asyncio.QueueFull:
                sub.queue.get_nowait()
                sub.queue.put_nowait(None)
        self._subscribers.clear()

    def _drop(self, queue: asyncio.Queue[StampedEvent | None]) -> None:
        self._subscribers = [sub for sub in self._subscribers if sub.queue is not queue]


def _is_visible_text_channel(stamped: StampedEvent, channel: str | None) -> bool:
    """Filter text deltas while leaving non-text Journal events visible."""

    if channel is None or channel == TEXT_CHANNEL_ALL:
        return True
    event = stamped.event
    if not isinstance(event, StepTextDelta):
        return True
    return getattr(event, "channel", "decision") == channel


def encode_live_gap(gap: LiveGap) -> bytes:
    """Encode an evicted replay range using the established SSE envelope."""

    payload = json.dumps(
        {"requested_seq": gap.requested_seq, "oldest_seq": gap.oldest_seq},
        ensure_ascii=False,
    )
    return f"event: LiveGap\ndata: {payload}\n\n".encode()


async def iter_live_sse(
    tail: LiveRunProjection,
    *,
    after_seq: int = 0,
    heartbeat_s: float = _HEARTBEAT_INTERVAL_S,
    text_channel: str | None = TEXT_CHANNEL_ANSWER,
) -> AsyncIterator[bytes]:
    """Serialize a journal tail as SSE frames with filtering and heartbeats."""

    sub = tail.subscribe(after_seq=after_seq)
    while True:
        try:
            item = await asyncio.wait_for(sub.__anext__(), timeout=heartbeat_s)
        except TimeoutError:
            yield _HEARTBEAT
            continue
        except StopAsyncIteration:
            break
        if isinstance(item, LiveGap):
            yield encode_live_gap(item)
            continue
        if not isinstance(item, StampedEvent):
            continue
        if not _is_visible_text_channel(item, text_channel):
            continue
        yield stamped_to_sse_frame(item).encode()


__all__ = [
    "TEXT_CHANNEL_ALL",
    "TEXT_CHANNEL_ANSWER",
    "LiveGap",
    "LiveTail",
    "encode_live_gap",
    "iter_live_sse",
]
