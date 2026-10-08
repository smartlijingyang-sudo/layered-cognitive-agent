"""Convergence runtime facade — evidence, verdict, synthesis (ADR-0196)."""

from __future__ import annotations

from dataclasses import dataclass, field

from lca.cognition.convergence.delivery_synth import synthesize_delivery_response
from lca.cognition.convergence.evidence import build_delivery_evidence
from lca.cognition.convergence.policy import DefaultConvergencePolicy
from lca.contracts.models.cognition.source_verify import VerifyDecision
from lca.contracts.models.core.policy.convergence import ConvergenceVerdict, DeliveryEvidence
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.think.convergence import ConvergencePolicy
from lca.infrastructure.session.emit.convergence_emit import (
    emit_convergence_evaluated,
    emit_delivery_evidence,
)
from lca.infrastructure.source_verify.policy import VerifyPolicy
from lca.infrastructure.source_verify.registry import SourceRegistry
from lca.infrastructure.source_verify.verifier import verify_final_answer as verify_source_answer


@dataclass(frozen=True, slots=True)
class ConvergenceRuntime:
    """Profile-selected convergence control plane seam for gates and stop."""

    policy: ConvergencePolicy
    source_registry: SourceRegistry = field(default_factory=SourceRegistry)

    @classmethod
    def default(cls) -> ConvergenceRuntime:
        return cls(policy=DefaultConvergencePolicy(), source_registry=SourceRegistry())

    def evidence(self, state: AgentState) -> DeliveryEvidence:
        return build_delivery_evidence(state)

    def evaluate(self, state: AgentState, *, evidence: DeliveryEvidence) -> ConvergenceVerdict:
        return self.policy.evaluate(state, evidence=evidence)

    def evaluate_budget_exhausted(
        self,
        state: AgentState,
        *,
        evidence: DeliveryEvidence,
    ) -> ConvergenceVerdict:
        evaluate_budget = getattr(self.policy, "evaluate_budget_exhausted", None)
        if callable(evaluate_budget):
            result = evaluate_budget(state, evidence=evidence)
            if isinstance(result, ConvergenceVerdict):
                return result
            # Fallback if the dynamic method returns something unexpected
            return ConvergenceVerdict(
                kind="grace_respond",
                rationale="budget exhausted (dynamic evaluator returned non-verdict)",
                evidence=evidence,
            )
        if evidence.satisfied:
            return ConvergenceVerdict(
                kind="grace_respond",
                rationale="budget exhausted after delivery satisfied",
                evidence=evidence,
            )
        return ConvergenceVerdict(
            kind="force_stop",
            rationale=evidence.detail or "budget exhausted without delivery",
            evidence=evidence,
        )

    def synthesize(
        self,
        state: AgentState,
        evidence: DeliveryEvidence,
        *,
        existing_text: str = "",
    ) -> str:
        response = synthesize_delivery_response(state, evidence, existing_text=existing_text)
        self.verify_final_answer(state, response)
        return response

    def verify_final_answer(self, state: AgentState, answer: str) -> VerifyDecision:
        """Verify a user-facing answer in WARN mode without changing its text."""
        return verify_source_answer(answer, self.source_registry, VerifyPolicy.default())

    def evaluate_and_emit(
        self,
        state: AgentState,
        *,
        evidence: DeliveryEvidence | None = None,
    ) -> tuple[DeliveryEvidence, ConvergenceVerdict]:
        resolved = evidence if evidence is not None else self.evidence(state)
        emit_delivery_evidence(state, resolved)
        verdict = self.evaluate(state, evidence=resolved)
        emit_convergence_evaluated(state, verdict)
        return resolved, verdict

    def evaluate_budget_and_emit(
        self,
        state: AgentState,
        *,
        evidence: DeliveryEvidence | None = None,
    ) -> tuple[DeliveryEvidence, ConvergenceVerdict]:
        resolved = evidence if evidence is not None else self.evidence(state)
        emit_delivery_evidence(state, resolved)
        verdict = self.evaluate_budget_exhausted(state, evidence=resolved)
        emit_convergence_evaluated(state, verdict)
        return resolved, verdict


__all__ = ["ConvergenceRuntime"]
