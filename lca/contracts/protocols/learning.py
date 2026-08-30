"""Cross-layer contracts for candidate-only learning services.

Learning services may derive review artifacts from durable evidence, but they do
not materialize installed skills or modify a production Profile. Keeping these
small value models and Protocols in ``contracts`` lets lifecycle-level
orchestration depend on stable interfaces rather than concrete implementations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from lca.contracts.models.core.lifecycle import TaskStatus


@dataclass(frozen=True, slots=True)
class SkillAcquisitionCandidate:
    """A non-promoted procedural-skill draft with traceable source evidence."""

    candidate_id: str
    task_ref: str
    procedure: str
    confidence: float
    evidence_refs: tuple[str, ...]
    status: str = "draft"


@runtime_checkable
class SkillAcquirer(Protocol):
    """Produce only evidence-gated procedural-skill candidates."""

    def propose(
        self,
        *,
        task_ref: str,
        procedure: str,
        success: bool,
        confidence: float,
        evidence_refs: tuple[str, ...],
    ) -> SkillAcquisitionCandidate | None: ...


@dataclass(frozen=True, slots=True)
class FailureAnalysis:
    """A replayable failure diagnosis tied to a trigger and evidence references."""

    run_ref: str
    trigger: str
    root_cause: str
    evidence_refs: tuple[str, ...]
    suggestions: tuple[str, ...]


@runtime_checkable
class FailureAnalyzer(Protocol):
    """Derive non-authoritative analyses for an allowlisted failure trigger."""

    def analyze(
        self,
        *,
        run_ref: str,
        trigger: str,
        evidence_refs: tuple[str, ...],
        summary: str = "",
    ) -> FailureAnalysis | None: ...


class LearningReviewTicketStatus(StrEnum):
    """Lifecycle of one durable review request, separate from Agent TaskStatus."""

    QUEUED = "queued"
    CLAIMED = "claimed"
    ASSESSED = "assessed"


@dataclass(frozen=True, slots=True)
class LearningReviewTicket:
    """A review request containing only immutable evidence references.

    A claimed ticket carries an exclusive, time-bounded lease. The ticket never
    exposes a live Agent, mutable runtime state, an effect gateway, or a
    capability scope.
    """

    ticket_id: str
    trace_id: str
    plan_ref: str
    event_status: TaskStatus
    state_ref: str | None
    journal_sequence: int | None
    status: LearningReviewTicketStatus = LearningReviewTicketStatus.QUEUED
    lease_id: str | None = None
    lease_worker_id: str | None = None
    lease_acquired_at: datetime | None = None
    lease_expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class LearningReviewAssessment:
    """A candidate-only outcome attached to one claimed terminal review ticket."""

    ticket_id: str
    skill_candidate: SkillAcquisitionCandidate | None = None
    failure_analysis: FailureAnalysis | None = None


@runtime_checkable
class LearningReviewTicketStore(Protocol):
    """Durable, idempotent queue for candidate-only terminal review requests.

    Implementations own storage and lease transitions only. They must not load
    referenced evidence, call an LLM, write installed skills, or publish a
    Profile. An event key identifies a terminal lifecycle fact and suppresses
    duplicate ticket creation across process restarts.
    """

    def enqueue(
        self,
        *,
        event_key: str,
        ticket: LearningReviewTicket,
        max_pending: int,
    ) -> LearningReviewTicket | None: ...

    def tickets(self) -> tuple[LearningReviewTicket, ...]: ...

    def assessments(self) -> tuple[LearningReviewAssessment, ...]: ...

    def claim_next(
        self,
        worker_id: str,
        *,
        now: datetime,
        lease_seconds: int,
    ) -> LearningReviewTicket | None: ...

    def release(
        self,
        ticket_id: str,
        *,
        lease_id: str,
        worker_id: str,
        now: datetime,
    ) -> LearningReviewTicket: ...

    def complete_assessment(
        self,
        assessment: LearningReviewAssessment,
        *,
        lease_id: str,
        worker_id: str,
        now: datetime,
    ) -> LearningReviewTicket: ...


__all__ = [
    "FailureAnalysis",
    "FailureAnalyzer",
    "LearningReviewAssessment",
    "LearningReviewTicket",
    "LearningReviewTicketStatus",
    "LearningReviewTicketStore",
    "SkillAcquirer",
    "SkillAcquisitionCandidate",
]
