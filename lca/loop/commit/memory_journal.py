"""Memory journal commit seam (ADR-0194 P1-13).

Prepared :class:`MemoryJournalReceipt` / :class:`MemorySpineReceipt` from cognition
memory commit here via :class:`FactGateway`.
"""

from __future__ import annotations

from dataclasses import asdict

from lca.contracts.harness.memory.events import ContextCompactedCommitted, MemoryCommittedCommitted
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.models.observability.journal.journal import (
    ContextCompacted,
    JournalEvent,
    MemoryCommitted,
)
from lca.contracts.models.observability.memory.journal_receipt import (
    MemoryJournalReceipt,
    MemorySpineReceipt,
)
from lca.contracts.protocols.loop.fact_gateway import AppendReceipt, SessionCatalogEvent
from lca.loop.fact_gateway import append_catalog_bound, publish_ep_bound


def _catalog_from_journal(event: JournalEvent) -> SessionCatalogEvent:
    if isinstance(event, MemoryCommitted):
        return MemoryCommittedCommitted(**asdict(event))
    if isinstance(event, ContextCompacted):
        return ContextCompactedCommitted(**asdict(event))
    msg = f"unsupported memory journal event type: {type(event).__name__}"
    raise TypeError(msg)


def commit_memory_journal_receipt(
    receipt: MemoryJournalReceipt,
    *,
    state: AgentState | None = None,
    session: object | None = None,
) -> AppendReceipt | None:
    """Commit one prepared memory catalog fact via FactGateway; no-op if unbound."""
    catalog = _catalog_from_journal(receipt.journal_event)
    return append_catalog_bound(
        catalog,
        state=state,
        session=session,
        actor=receipt.actor,
    )


def commit_memory_spine_receipt(
    receipt: MemorySpineReceipt,
    *,
    state: AgentState | None = None,
    session: object | None = None,
) -> AppendReceipt | None:
    """Commit one memory spine EP via FactGateway; no-op if session unbound."""
    return publish_ep_bound(
        receipt.ep,
        receipt.payload,
        state=state,
        session=session,
        actor=receipt.actor,
    )


__all__ = ["commit_memory_journal_receipt", "commit_memory_spine_receipt"]
