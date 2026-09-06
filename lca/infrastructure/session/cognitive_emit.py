"""Gate / perceive Session fact production (ADR-0191 R2).

Single production seam for ``gate.decided.v1`` and ``context.manifested.v1``.
All helpers no-op when no Session is bound (tests / offline).
"""

from __future__ import annotations

from typing import Any

from lca.contracts.harness.memory.events import (
    ContextManifestCommitted,
    GateDecidedCommitted,
)
from lca.contracts.models.core.gate_policy import GateDecided
from lca.contracts.models.core.perception import ContextItem, ContextManifest
from lca.contracts.models.core.state import AgentState
from lca.harness.session.emit import emit
from lca.infrastructure.session.bindings import resolve_session_for_emit


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
) -> Any | None:
    """Append one ``gate.decided.v1`` fact."""
    return emit(session, event, actor=actor)


def emit_gate_decided_from_policy(
    state: AgentState,
    event: GateDecided,
    *,
    session: object | None = None,
    actor: str = "gate",
) -> Any | None:
    """Map contracts ``GateDecided`` → session fact; no-op if unbound."""
    writer = session if session is not None else resolve_session_for_emit(state)
    if writer is None:
        return None
    return emit_gate_decided(
        writer,
        _gate_decided_committed(event, step=state.step),
        actor=actor,
    )


def emit_context_manifested(
    session: object,
    manifest: ContextManifest,
    *,
    step: int,
    actor: str = "perceive",
) -> Any | None:
    """Append one ``context.manifested.v1`` fact."""
    return emit(
        session,
        ContextManifestCommitted(
            step=step,
            digest=manifest.digest,
            items=tuple(_context_item_wire(item) for item in manifest.items),
        ),
        actor=actor,
    )


def emit_context_manifested_for_state(
    state: AgentState,
    manifest: ContextManifest,
    *,
    session: object | None = None,
    actor: str = "perceive",
) -> Any | None:
    """Resolve session from run context, then emit manifest fact."""
    writer = session if session is not None else resolve_session_for_emit(state)
    if writer is None:
        return None
    return emit_context_manifested(writer, manifest, step=state.step, actor=actor)


__all__ = [
    "emit_context_manifested",
    "emit_context_manifested_for_state",
    "emit_gate_decided",
    "emit_gate_decided_from_policy",
]
