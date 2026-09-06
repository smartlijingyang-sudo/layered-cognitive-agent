"""Gate / perceive / think Session fact production (ADR-0191 R2, ADR-0194 P1-06/14).

Single production seam for ``gate.decided.v1``, ``context.manifested.v1``, and
``brain.think.start`` / ``brain.think.end`` spine EPs (via ``publish_ep_bound``).
All helpers no-op when no Session is bound (tests / offline).
"""

from __future__ import annotations

import contextlib
from typing import Any

from lca.contracts.harness.memory.events import (
    ContextManifestCommitted,
    GateDecidedCommitted,
)
from lca.contracts.models.core.decision import Decision
from lca.contracts.models.core.gate_policy import GateDecided
from lca.contracts.models.core.perception import ContextItem, ContextManifest
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import Brain
from lca.contracts.protocols.loop.fact_gateway import AppendReceipt
from lca.loop.fact_gateway import append_catalog_bound, publish_ep_bound


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


def emit_brain_think_start_for_state(
    state: AgentState,
    *,
    session: object | None = None,
    actor: str = "brain",
) -> AppendReceipt | None:
    """Append one ``brain.think.start`` spine fact."""
    return publish_ep_bound(
        "brain.think.start",
        {"state_id": state.trace_id},
        state=state,
        session=session,
        actor=actor,
    )


def emit_brain_think_end_for_state(
    state: AgentState,
    *,
    outcome: str = "success",
    session: object | None = None,
    actor: str = "brain",
) -> AppendReceipt | None:
    """Append one ``brain.think.end`` spine fact."""
    return publish_ep_bound(
        "brain.think.end",
        {"state_id": state.trace_id, "outcome": outcome},
        state=state,
        session=session,
        actor=actor,
    )


async def run_brain_think_with_spine_facts(brain: Brain, state: AgentState) -> Decision:
    """Run ``brain.think`` with ``brain.think.start/end`` facts via FactGateway.

    Spine mirror failures must not block cognition (same contract as the former
    ``ModularBrain`` inline envelope).
    """
    with contextlib.suppress(Exception):
        emit_brain_think_start_for_state(state)
    try:
        decision = await brain.think(state)
    except BaseException:
        with contextlib.suppress(Exception):
            emit_brain_think_end_for_state(state, outcome="failure")
        raise
    with contextlib.suppress(Exception):
        emit_brain_think_end_for_state(state, outcome="success")
    return decision


__all__ = [
    "emit_brain_think_end_for_state",
    "emit_brain_think_start_for_state",
    "emit_context_manifested",
    "emit_context_manifested_for_state",
    "emit_gate_decided",
    "emit_gate_decided_from_policy",
    "run_brain_think_with_spine_facts",
]
