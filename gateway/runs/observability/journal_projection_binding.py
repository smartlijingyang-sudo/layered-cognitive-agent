"""Lifecycle owner for the gateway's process-wide journal projection."""

from __future__ import annotations

from lca.contracts.observability.run_journal import ProcessJournalProjection, RunJournalFactory
from lca.contracts.protocols import JournalProjector


class ProcessJournalBinding:
    """Lazily close the one process projection shared by all legacy runs.

    Individual runs receive lightweight bound projectors. Closing a run must
    never dispose this process-level live projection, so its lifecycle is kept
    out of both ``RunSession`` and the in-memory run index.
    """

    def __init__(self) -> None:
        self._journal: ProcessJournalProjection | None = None

    @property
    def journal(self) -> ProcessJournalProjection:
        """Return the bound projection or reject an implicit default."""

        if self._journal is None:
            raise RuntimeError(
                "process journal is not bound; create a run through a journal factory"
            )
        return self._journal

    def bind(self, factory: RunJournalFactory) -> JournalProjector:
        """Create the projection once and return a per-run append binding."""

        if self._journal is None:
            self._journal = factory.create_process_journal()
        return self._journal.bind()

    @property
    def subscriber_count(self) -> int:
        """Expose live subscription pressure without leaking the projection field."""

        return self._journal.tail.subscriber_count if self._journal is not None else 0


__all__ = ["ProcessJournalBinding"]
