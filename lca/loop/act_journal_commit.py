"""Act journal commit seam (ADR-0194 P1-11).

Prepared :class:`ActJournalReceipt` from cognition body commits here. Legacy
``JournalEvent`` types use ``append_journal_event`` until Session catalog migration.
"""

from __future__ import annotations

from lca.contracts.models.core.state import AgentState
from lca.contracts.models.observability.act_journal_receipt import ActJournalReceipt
from lca.contracts.models.observability.journal import StampedEvent
from lca.infrastructure.observability.journal_append import append_journal_event


def commit_act_journal_receipt(
    receipt: ActJournalReceipt,
    *,
    state: AgentState | None = None,
    session: object | None = None,
) -> StampedEvent | None:
    """Commit one prepared act journal fact; no-op when journal unbound."""
    del state, session
    return append_journal_event(receipt.journal_event)


__all__ = ["commit_act_journal_receipt"]
