"""Gate / perceive catalog fact emitters (ADR-0191 R2, ADR-0194 P1-06/14).

Single production seam for ``gate.decided.v1`` and ``context.manifested.v1``
catalog facts. All helpers no-op when no Session is bound (tests / offline).
"""

from __future__ import annotations

from typing import Any

from lca.contracts.harness.memory.events import (
    ContextManifestCommitted,
    GateDecidedCommitted,
)
from lca.contracts.models.core.perceive.perception import ContextItem, ContextManifest
from lca.contracts.models.core.policy.gate_policy import GateDecided
from lca.contracts.models.core.state.state import AgentState
from lca.infrastructure.session.emit.cognitive_emit.envelope import (
    AppendReceipt,
    append_catalog_bound,
)


def _gate_decided_committed(event: GateDecided, *, step: int) -> GateDecidedCommitted:
    fact = event.policy_fact
    return GateDecidedCommitted(
        event_id=event.event_id,
        gate=event.gate,
        verdict=event.verdict,
        is_rewritten=event.is_rewritten,
        step=step,
        policy_fact_kind=fact.kind if fact is not None else "",
        policy_fact_message=fact.message if fact is not None else "",
        policy_fact_source=fact.source if fact is not None else "",
        tool_name=event.tool_name,
        rationale=event.rationale,
    )


def _context_item_wire(item: ContextItem) -> dict[str, Any]:
    return {
        "kind": item.kind,
        "payload_repr": repr(item.payload),
        "provenance": item.provenance,
        "extra": dict(item.extra),
    }


def emit_gate_decided(
    session: object,
    event: GateDecidedCommitted,
    *,
    actor: str = "gate",
) -> AppendReceipt | None:
    """Append one ``gate.decided.v1`` fact."""
    return append_catalog_bound(event, session=session, actor=actor)


def emit_gate_decided_from_policy(
    state: AgentState,
    event: GateDecided,
    *,
    session: object | None = None,
    actor: str = "gate",
) -> AppendReceipt | None:
    """Map contracts ``GateDecided`` → session fact; no-op if unbound."""
    return append_catalog_bound(
        _gate_decided_committed(event, step=state.step),
        state=state,
        session=session,
        actor=actor,
    )


def emit_context_manifested(
    session: object,
    manifest: ContextManifest,
    *,
    step: int,
    actor: str = "perceive",
) -> AppendReceipt | None:
    """Append one ``context.manifested.v1`` fact."""
    return append_catalog_bound(
        ContextManifestCommitted(
            step=step,
            digest=manifest.digest,
            items=tuple(_context_item_wire(item) for item in manifest.items),
        ),
        session=session,
        actor=actor,
    )


def emit_context_manifested_for_state(
    state: AgentState,
    manifest: ContextManifest,
    *,
    session: object | None = None,
    actor: str = "perceive",
) -> AppendReceipt | None:
    """Resolve session from run context, then emit manifest fact."""
    return append_catalog_bound(
        ContextManifestCommitted(
            step=state.step,
            digest=manifest.digest,
            items=tuple(_context_item_wire(item) for item in manifest.items),
        ),
        state=state,
        session=session,
        actor=actor,
    )


__all__ = [
    "emit_context_manifested",
    "emit_context_manifested_for_state",
    "emit_gate_decided",
    "emit_gate_decided_from_policy",
]
