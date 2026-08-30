"""Health projections for the process-local run registry.

This module owns the carrier-facing health view assembled from the ephemeral
run index and the process-level journal binding.  ``RunRegistry`` retains and
coordinates those collaborators; it does not know the shape of the health
projection.
"""

from __future__ import annotations

from gateway.runs.observability.journal_projection_binding import ProcessJournalBinding
from gateway.runs.session.index import RunSessionIndex


class RunHealthProjection:
    """Project run-index and journal pressure facts into one health view."""

    def __init__(
        self,
        *,
        index: RunSessionIndex,
        process_journal: ProcessJournalBinding,
    ) -> None:
        self._index = index
        self._process_journal = process_journal

    def status_counts(self) -> dict[str, int]:
        """Return status counts owned by the retained-session index."""

        return self._index.status_counts()

    def live_totals(self) -> dict[str, int]:
        """Combine run-tail pressure with process-journal subscriber pressure."""

        totals = self._index.live_tail_totals()
        totals["journal_subscribers"] = self._process_journal.subscriber_count
        return totals


__all__ = ["RunHealthProjection"]
