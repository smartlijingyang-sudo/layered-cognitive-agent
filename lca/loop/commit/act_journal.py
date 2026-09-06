"""Act journal commit seam (ADR-0194 P1-11).

Prepared :class:`ActJournalReceipt` from cognition body commits here via
:class:`FactGateway` (``append_catalog_bound``).
"""

from __future__ import annotations

from dataclasses import asdict

from lca.contracts.harness.memory.events import (
    ApprovalRequestedCommitted,
    DecisionMadeCommitted,
    SynthesisCompletedCommitted,
    TeamMessagePublishedCommitted,
)
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.models.observability.act.act_journal_receipt import ActJournalReceipt
from lca.contracts.models.observability.journal.journal import (
    ApprovalRequested,
    DecisionMade,
    JournalEvent,
    SynthesisCompleted,
    TeamMessagePublished,
)
from lca.contracts.protocols.loop.fact_gateway import AppendReceipt, SessionCatalogEvent
from lca.loop.fact_gateway import append_catalog_bound


def _catalog_from_journal(event: JournalEvent) -> SessionCatalogEvent:
    if isinstance(event, DecisionMade):
        return DecisionMadeCommitted(**asdict(event))
    if isinstance(event, ApprovalRequested):
        return ApprovalRequestedCommitted(**asdict(event))
    if isinstance(event, SynthesisCompleted):
        return SynthesisCompletedCommitted(**asdict(event))
    if isinstance(event, TeamMessagePublished):
        return TeamMessagePublishedCommitted(**asdict(event))
    msg = f"unsupported act journal event type: {type(event).__name__}"
    raise TypeError(msg)


def commit_act_journal_receipt(
    receipt: ActJournalReceipt,
    *,
    state: AgentState | None = None,
    session: object | None = None,
) -> AppendReceipt | None:
    """Commit one prepared act catalog fact via FactGateway; no-op if unbound."""
    catalog = _catalog_from_journal(receipt.journal_event)
    return append_catalog_bound(
        catalog,
        state=state,
        session=session,
        actor=receipt.actor,
    )


__all__ = ["commit_act_journal_receipt"]
