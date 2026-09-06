"""Default convergence policy — operational + delivery layers (ADR-0196)."""

from __future__ import annotations

from lca.contracts.models.core.policy.convergence import (
    ConvergenceVerdict,
    DeliveryEvidence,
)
from lca.contracts.models.core.state.state import AgentState


class DefaultConvergencePolicy:
    """Map delivery evidence to a convergence verdict for gates and stop."""

    def evaluate(self, state: AgentState, *, evidence: DeliveryEvidence) -> ConvergenceVerdict:
        del state
        if evidence.satisfied:
            return ConvergenceVerdict(
                kind="force_respond",
                rationale=evidence.detail,
                evidence=evidence,
            )
        if evidence.producer_success_since_task >= 3 and evidence.task_class == "informative_text":
            return ConvergenceVerdict(
                kind="nudge",
                rationale="多次 producer 成功但未收口；应 text respond",
                evidence=evidence,
            )
        return ConvergenceVerdict(
            kind="continue",
            rationale=evidence.detail or "continue",
            evidence=evidence,
        )

    def evaluate_budget_exhausted(
        self,
        state: AgentState,
        *,
        evidence: DeliveryEvidence,
    ) -> ConvergenceVerdict:
        del state
        if evidence.satisfied:
            return ConvergenceVerdict(
                kind="grace_respond",
                rationale="budget exhausted after delivery satisfied; synthesize final output",
                evidence=evidence,
            )
        return ConvergenceVerdict(
            kind="force_stop",
            rationale=evidence.detail or "budget exhausted without delivery",
            evidence=evidence,
        )


__all__ = ["DefaultConvergencePolicy"]
