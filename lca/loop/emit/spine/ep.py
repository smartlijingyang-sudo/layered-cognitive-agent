"""Spine execution-point commit seam (ADR-0194 P2-13..15).

All durable spine EP facts route through ``FactGateway.publish_ep`` via
``publish_ep_bound``. Returns a lightweight ref for callers/tests that
previously read ``EventRef.category``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.loop.fact_gateway import AppendReceipt
from lca.loop.fact_gateway import publish_ep_bound
from lca_kernel.events.payloads_spine import _SPINE_EP_TO_CATEGORY


@dataclass(frozen=True)
class SpineEmitRef:
    """Backward-compatible publish receipt (category + append metadata)."""

    category: str
    event_type: str
    seq: int | None = None


def publish_spine_ep(
    execution_point: str,
    payload: dict[str, Any],
    *,
    channel: str = "fact",
    actor: str = "spine",
    state: AgentState | None = None,
    session: object | None = None,
) -> SpineEmitRef | None:
    """Commit one spine EP via FactGateway; no-op when session unbound."""
    del channel  # enrich seam reads channel from active hook when needed
    receipt = publish_ep_bound(
        execution_point,
        payload,
        state=state,
        session=session,
        actor=actor,
    )
    if receipt is None:
        return None
    category = _SPINE_EP_TO_CATEGORY[execution_point]
    return SpineEmitRef(
        category=category,
        event_type=receipt.event_type,
        seq=receipt.seq,
    )


def receipt_or_none(receipt: AppendReceipt | None) -> SpineEmitRef | None:
    """Map ``AppendReceipt`` to ``SpineEmitRef`` (category = session event type)."""
    if receipt is None:
        return None
    return SpineEmitRef(
        category=receipt.event_type,
        event_type=receipt.event_type,
        seq=receipt.seq,
    )


__all__ = ["SpineEmitRef", "publish_spine_ep", "receipt_or_none"]
