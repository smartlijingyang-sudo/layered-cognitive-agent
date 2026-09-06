"""Convergence session fact production (ADR-0196)."""

from __future__ import annotations

from lca.contracts.harness.memory.events import (
    ConvergenceEvaluatedCommitted,
    DeliveryEvidenceCommitted,
    PromptSurfaceRenderedCommitted,
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
            task_class=evidence.task_class,
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
            task_class=verdict.evidence.task_class,
            satisfied=verdict.evidence.satisfied,
            detail=verdict.evidence.detail,
        ),
        state=state,
        session=session,
        actor=actor,
    )


def emit_prompt_surface_rendered(
    state: AgentState,
    *,
    step: int,
    task_class: str,
    tool_count: int,
    include_full_sandbox: bool,
    digest: str,
    session: object | None = None,
    actor: str = "prompt_surface",
) -> AppendReceipt | None:
    return append_catalog_bound(
        PromptSurfaceRenderedCommitted(
            step=step,
            task_class=task_class,
            tool_count=tool_count,
            include_full_sandbox=include_full_sandbox,
            digest=digest,
        ),
        state=state,
        session=session,
        actor=actor,
    )


__all__ = [
    "emit_convergence_evaluated",
    "emit_delivery_evidence",
    "emit_prompt_surface_rendered",
]
