"""Construct minimal immutable state snapshots for passive phase observers."""

from __future__ import annotations

from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.journal.phase_observation import (
    PhaseBudgetSnapshot,
    PhaseStateSnapshot,
)


def phase_state_snapshot(state: object) -> PhaseStateSnapshot:
    """Capture observer-safe metadata without exposing the live state object.

    Production runtimes provide :class:`AgentState`. The generic declarative
    harness also deliberately accepts opaque state carriers for topology tests;
    those carriers receive an anonymous, zero-budget snapshot rather than a
    structural ``getattr`` probe or an accidental live-state backchannel.
    """

    if not isinstance(state, AgentState):
        return PhaseStateSnapshot(
            trace_id="",
            agent_role="",
            step=0,
            status=TaskStatus.WORKING,
            budget=PhaseBudgetSnapshot(
                max_tokens=None,
                max_cost_usd=None,
                max_steps=None,
                max_wall_clock_seconds=None,
                used_tokens=0,
                used_cost_usd=0.0,
                used_steps=0,
            ),
        )
    return PhaseStateSnapshot(
        trace_id=state.trace_id,
        agent_role=state.agent_role,
        step=state.step,
        status=state.status,
        budget=PhaseBudgetSnapshot(
            max_tokens=state.budget.max_tokens,
            max_cost_usd=state.budget.max_cost_usd,
            max_steps=state.budget.max_steps,
            max_wall_clock_seconds=state.budget.max_wall_clock_seconds,
            used_tokens=state.budget.used_tokens,
            used_cost_usd=state.budget.used_cost_usd,
            used_steps=state.budget.used_steps,
        ),
    )


__all__ = ["phase_state_snapshot"]
