"""Stable protocol for policy-governed declarative loop re-entry.

The phase graph remains the source of loop topology.  A profile-selected
``LoopGuardEvaluator`` decides whether a concrete guarded edge may re-enter
that topology after its ordinary edge predicate matched.  This keeps resource
limits and terminal conditions replaceable without giving plugins authority to
mutate state, execute effects, or alter the phase graph.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.declarative_execution import PhaseResult
from lca.contracts.protocols.declarative_graph import LoopGuard, PhaseEdge


@dataclass(frozen=True, slots=True)
class LoopGuardVerdict:
    """One explicit decision about whether a guarded edge may re-enter a loop."""

    allow: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.allow and not self.reason:
            raise ValueError("a denied loop guard verdict requires a reason")
        if self.allow and self.reason is not None:
            raise ValueError("an allowed loop guard verdict must not carry a denial reason")


@runtime_checkable
class LoopGuardEvaluator(Protocol):
    """Evaluate one declaratively guarded edge without ambient runtime access."""

    def evaluate(
        self,
        *,
        guard: LoopGuard,
        edge: PhaseEdge,
        state: AgentState,
        result: PhaseResult,
        artifacts: Mapping[str, object],
    ) -> LoopGuardVerdict: ...


__all__ = ["LoopGuardEvaluator", "LoopGuardVerdict"]
