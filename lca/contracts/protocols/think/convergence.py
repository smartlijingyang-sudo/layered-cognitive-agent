"""ConvergencePolicy protocol — semantic stop / delivery (ADR-0196)."""

from __future__ import annotations

from typing import Protocol

from lca.contracts.models.core.policy.convergence import ConvergenceVerdict, DeliveryEvidence
from lca.contracts.models.core.state.state import AgentState


class ConvergencePolicy(Protocol):
    """Evaluate whether the run should continue, nudge, or force closure."""

    def evaluate(self, state: AgentState, *, evidence: DeliveryEvidence) -> ConvergenceVerdict: ...

    def evaluate_budget_exhausted(
        self,
        state: AgentState,
        *,
        evidence: DeliveryEvidence,
    ) -> ConvergenceVerdict: ...


__all__ = ["ConvergencePolicy"]
