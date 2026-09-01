"""EventSink Protocol — write EventRecord to a backing store.

A sink is the destination of truth. There is exactly one EventSink per
spine in production (FileSink), but the Protocol allows test doubles.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.infrastructure.observability.spine.event_record import EventRecord


@runtime_checkable
class EventSink(Protocol):
    """A destination for spine events."""

    def write(self, record: EventRecord) -> None:
        ...

    def close(self) -> None:
        ...
