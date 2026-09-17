"""Convergence session fact production (ADR-0196)."""

from __future__ import annotations

from lca.contracts.harness.memory.events import (
    ConvergenceEvaluatedCommitted,
    DeliveryEvidenceCommitted,
)
from lca.contracts.models.core.policy.convergence import ConvergenceVerdict, DeliveryEvidence
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.loop.fact_gateway import AppendReceipt
from lca.loop.fact_gateway import append_catalog_bound


def emit_delivery_evidence(
    state: AgentState,
    evidence: DeliveryEvidence,
    *,
    session: object | None = None,
    actor: str = "convergence",
) -> AppendReceipt | None:
    return append_catalog_bound(
        DeliveryEvidenceCommitted(
            step=state.step,
            artifact_count=evidence.artifact_count,
            producer_success_count=evidence.producer_success_since_task,
            satisfied=evidence.satisfied,
            detail=evidence.detail,
        ),
        state=state,
        session=session,
        actor=actor,
    )


def emit_convergence_evaluated(
    state: AgentState,
    verdict: ConvergenceVerdict,
    *,
    session: object | None = None,
    actor: str = "convergence",
) -> AppendReceipt | None:
    return append_catalog_bound(
        ConvergenceEvaluatedCommitted(
            step=state.step,
            kind=verdict.kind,
            rationale=verdict.rationale,
            satisfied=verdict.evidence.satisfied,
            detail=verdict.evidence.detail,
        ),
        state=state,
        session=session,
        actor=actor,
    )


__all__ = [
    "emit_convergence_evaluated",
    "emit_delivery_evidence",
]
