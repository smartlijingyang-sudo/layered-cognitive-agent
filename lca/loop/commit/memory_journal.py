"""Memory journal commit seam (ADR-0194 P1-13).

Prepared :class:`MemoryJournalReceipt` / :class:`MemorySpineReceipt` from cognition
memory commit here. Legacy ``JournalEvent`` types use ``append_journal_event`` until
Session catalog migration; spine EPs use ``FactGateway.publish_ep``.
"""

from __future__ import annotations

from lca.contracts.models.core.state import AgentState
from lca.contracts.models.observability.journal import StampedEvent
from lca.contracts.models.observability.memory_journal_receipt import (
    MemoryJournalReceipt,
    MemorySpineReceipt,
)
from lca.contracts.protocols.loop.fact_gateway import AppendReceipt
from lca.infrastructure.observability.journal_append import append_journal_event
from lca.loop.fact_gateway import publish_ep_bound


def commit_memory_journal_receipt(
    receipt: MemoryJournalReceipt,
    *,
    state: AgentState | None = None,
    session: object | None = None,
) -> StampedEvent | None:
    """Commit one prepared memory journal fact; no-op when journal unbound."""
    del state, session
    return append_journal_event(receipt.journal_event)


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
