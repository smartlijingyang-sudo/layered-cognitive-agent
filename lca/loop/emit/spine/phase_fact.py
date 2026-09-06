"""Phase-scoped catalog fact emission (ADR-0192 E1).

Called from ``PhaseExecutionTransaction`` after a successful phase visit.
Imports are lazy to avoid harness ↔ infrastructure session binding cycles.
"""

from __future__ import annotations

from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    PhaseResult,
    SemanticPhase,
)


def _current_cursor():
    from lca.infrastructure.observability.loop_cursor.coordinator.coordinator_adapter import (
        current_cursor,
    )

    return current_cursor()


def emit_phase_catalog_facts(
    *,
    semantic_phase: SemanticPhase,
    result: PhaseResult,
    state: AgentState,
) -> None:
    """Emit DSH-aligned catalog facts and phase fold EPs for one completed visit."""
    if semantic_phase is SemanticPhase.PERCEIVE:
        _emit_perceive(result=result, state=state)
        return
    if semantic_phase is SemanticPhase.REMEMBER:
        _emit_remember(state=state)


def _emit_perceive(*, result: PhaseResult, state: AgentState) -> None:
    from lca.infrastructure.session.emit.cognitive_emit import emit_context_manifested_for_state
    from lca.infrastructure.session.emit.lifecycle_emit import begin_step

    step = getattr(state, "step", 0) + 1
    begin_step(step=step)
    payload = result.payload
    if isinstance(payload, ContextManifest) and payload.digest:
        emit_context_manifested_for_state(state, payload)
    cursor = _current_cursor()
    if cursor is not None:
        cursor.advance("perceive")


def _emit_remember(*, state: AgentState) -> None:
    from lca.infrastructure.session.emit.lifecycle_emit import end_step

    step = max(getattr(state, "step", 0), 1)
    end_step(step=step)


__all__ = ["emit_phase_catalog_facts"]
