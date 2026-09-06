"""Runtime journal adapter for declarative Turn execution.

The generic interpreter depends on ``JournalCommitter`` / ``FactCommitter``.
Production wiring uses :class:`SessionFactCommitter` (ADR-0192); the
``RuntimeJournal`` protocol exposes monotonic sequence for outcome projection.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.protocols.observability.fact_committer import FactCommitter
from lca.infrastructure.session.fact_committer import SessionFactCommitter


@runtime_checkable
class RuntimeJournal(FactCommitter, Protocol):
    """A Turn journal that also exposes its monotonic committed sequence."""

    @property
    def sequence(self) -> int: ...


class RuntimeJournalCommitter(SessionFactCommitter, RuntimeJournal):
    """Publish declarative facts through Session SSOT (ADR-0192)."""

    pass


__all__ = ["RuntimeJournal", "RuntimeJournalCommitter"]
