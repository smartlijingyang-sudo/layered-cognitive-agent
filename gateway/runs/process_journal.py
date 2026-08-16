"""Process-wide journal reader — one LiveTail for every Run in this gateway.

Per-run LiveTail seq restarts at 1. This remints a process seq so ops
can subscribe once and see every run's journal without colliding.
A bind() projector is a no-op on close: run teardown must not shut ops.
"""

from __future__ import annotations

from dataclasses import replace

from gateway.runs.live import LiveTail
from lca.contracts.models.observability.journal import StampedEvent
from lca.contracts.protocols import JournalProjector


class ProcessJournal:
    """Long-lived journal fan-in for ``lca-ops logs``."""

    def __init__(self) -> None:
        self.tail = LiveTail()
        self._seq = 0

    def bind(self) -> JournalProjector:
        return _BoundProcessJournal(self)

    def publish(self, stamped: StampedEvent) -> None:
        self._seq += 1
        self.tail.on_event(replace(stamped, seq=self._seq))


class _BoundProcessJournal(JournalProjector):
    def __init__(self, owner: ProcessJournal) -> None:
        self._owner = owner

    def on_event(self, stamped: StampedEvent) -> None:
        self._owner.publish(stamped)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None
