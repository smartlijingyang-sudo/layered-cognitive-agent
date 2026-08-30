"""Run journal assembly contracts.

A run has three deliberately separate observable views: a durable per-run writer,
a per-run live tail, and one process-wide live projection.  Gateway owns the
HTTP transport that consumes these views, but it must not choose or construct
their implementations.  A profile-selected factory closes that implementation
choice behind the contracts in this module.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from lca.contracts.models.observability.journal import StampedEvent
from lca.contracts.protocols.journal.journal import JournalProjector


@runtime_checkable
class LiveRunProjection(JournalProjector, Protocol):
    """A bounded, replayable live projection for one run.

    The yielded control objects are intentionally opaque to the contract.  The
    transport adapter that owns their wire representation interprets them,
    while a factory replacement only has to preserve ordered event delivery.
    """

    @property
    def buffer_size(self) -> int:
        """Number of currently replayable entries."""
        ...

    @property
    def subscriber_count(self) -> int:
        """Number of active live consumers."""
        ...

    @property
    def evicted(self) -> int:
        """Number of consumers removed after sustained overflow."""
        ...

    def subscribe(self, after_seq: int = 0) -> AsyncIterator[StampedEvent | object]:
        """Replay entries after ``after_seq`` and then yield live entries."""
        ...


@runtime_checkable
class ProcessJournalProjection(Protocol):
    """Long-lived process projection that can contribute to individual runs."""

    @property
    def tail(self) -> LiveRunProjection:
        """The process-wide live projection."""
        ...

    def bind(self) -> JournalProjector:
        """Create a run-scoped projector without transferring process ownership."""
        ...


@dataclass(frozen=True)
class RunJournalComponents:
    """Run-scoped writer and live tail created as one coherent unit."""

    writer: JournalProjector
    tail: LiveRunProjection


@runtime_checkable
class RunJournalFactory(Protocol):
    """Profile-selected factory for runtime journal projections.

    ``RunLocator`` remains the sole owner of physical path derivation.  The
    factory receives the resolved durable path and selects the writer, live
    tail and process-wide projection implementation without involving Gateway.
    """

    def create_run_components(self, *, jsonl_path: Path) -> RunJournalComponents:
        """Create the durable writer and live tail for one run."""
        ...

    def create_process_journal(self) -> ProcessJournalProjection:
        """Create the single long-lived projection for the current process."""
        ...


__all__ = [
    "LiveRunProjection",
    "ProcessJournalProjection",
    "RunJournalComponents",
    "RunJournalFactory",
]
