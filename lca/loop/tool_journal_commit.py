"""Tool journal catalog commit seam (ADR-0194 P1-10, P1-12).

Prepared receipts from cognition (body tool lifecycle, brain llm_turn) commit
here via FactGateway. Unbound session → no-op (legacy journal path retires).
"""

from __future__ import annotations

from lca.contracts.models.core.state import AgentState
from lca.contracts.models.observability.tool_journal_receipt import ToolJournalReceipt
from lca.contracts.protocols.loop.fact_gateway import AppendReceipt
from lca.loop.fact_gateway import append_catalog_bound


def commit_tool_journal_receipt(
    receipt: ToolJournalReceipt,
    *,
    state: AgentState | None = None,
    session: object | None = None,
) -> AppendReceipt | None:
    """Commit one prepared tool catalog fact via FactGateway; no-op if unbound."""
    return append_catalog_bound(
        receipt.catalog_event,
        state=state,
        session=session,
        actor=receipt.actor,
    )


__all__ = ["commit_tool_journal_receipt"]
