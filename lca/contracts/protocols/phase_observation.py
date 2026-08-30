"""Contracts for passive declarative phase observation.

These contracts describe only the read-only observation seam. Implementations
and composition stay outside ``contracts`` so observers cannot acquire runtime
control dependencies through their type surface. Observers receive an immutable,
minimal state snapshot rather than the live :class:`AgentState`; state mutation
remains exclusively behind the reducer and declared delta path.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.protocols.declarative_phase_graph import SemanticPhase


@dataclass(frozen=True, slots=True)
class PhaseBudgetSnapshot:
    """Immutable budget counters safe to expose to passive observers."""

    max_tokens: int | None
    max_cost_usd: float | None
    max_steps: int | None
    max_wall_clock_seconds: int | None
    used_tokens: int
    used_cost_usd: float
    used_steps: int


@dataclass(frozen=True, slots=True)
class PhaseStateSnapshot:
    """Minimal immutable state metadata available to a phase observer.

    The snapshot deliberately excludes working memory, artifacts, historical
    turns, checkpoints, final output, error fields, skills, and team awareness.
    Such mutable or potentially sensitive runtime data belongs to declared
    phase capabilities and must not become a passive-observation backchannel.
    """

    trace_id: str
    agent_role: str
    step: int
    status: TaskStatus
    budget: PhaseBudgetSnapshot


@runtime_checkable
class PhaseObserver(Protocol):
    """Bracket one semantic phase without access to mutable execution state."""

    def observe(
        self,
        *,
        semantic_phase: SemanticPhase,
        state: PhaseStateSnapshot,
    ) -> AbstractContextManager[object]: ...


@dataclass(frozen=True, slots=True)
class PhaseObserverContribution:
    """Describe one independently registered passive observer."""

    id: str
    observer: PhaseObserver
    priority: int = 100


@runtime_checkable
class PhaseObserverRegistry(Protocol):
    """Register and freeze observer contributions during profile boot."""

    def register(self, contribution: PhaseObserverContribution) -> None: ...

    def snapshot(self) -> tuple[PhaseObserverContribution, ...]: ...


__all__ = [
    "PhaseBudgetSnapshot",
    "PhaseObserver",
    "PhaseObserverContribution",
    "PhaseObserverRegistry",
    "PhaseStateSnapshot",
]
