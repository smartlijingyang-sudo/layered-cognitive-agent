"""Candidate-only terminal review ticket domain service.

This module owns no agent-loop control path. It works exclusively with immutable
terminal lifecycle projections and worker-supplied evidence references. Ticket
persistence and lease ownership are delegated to an injected protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.protocols.runtime.runtime_lifecycle import (
    RuntimeLifecycleEvent,
    RuntimeLifecycleEventType,
    RuntimeLifecycleSubscriber,
)
from lca.contracts.protocols.think.learning import (
    FailureAnalysis,
    FailureAnalyzer,
    LearningReviewAssessment,
    LearningReviewTicket,
    LearningReviewTicketStatus,
    LearningReviewTicketStore,
    SkillAcquirer,
    SkillAcquisitionCandidate,
)


@dataclass
class LearningReviewService(RuntimeLifecycleSubscriber):
    """Queue terminal review requests and assess only worker-supplied evidence.

    A worker may claim a ticket and retrieve its references through a separately
    governed read-only evidence interface. This service cannot retrieve source
    data itself and cannot materialize an installed skill or production Profile.
    """

    enabled: bool
    allowed_statuses: frozenset[TaskStatus]
    max_pending: int
    lease_seconds: int
    ticket_store: LearningReviewTicketStore
    skill_acquirer: SkillAcquirer
    failure_analyzer: FailureAnalyzer

    def __post_init__(self) -> None:
        if self.max_pending <= 0:
            raise ValueError("learning review max_pending must be positive")
        if self.lease_seconds <= 0:
            raise ValueError("learning review lease_seconds must be positive")
        if not isinstance(self.ticket_store, LearningReviewTicketStore):
            raise TypeError("learning review ticket_store must implement LearningReviewTicketStore")

    @property
    def tickets(self) -> tuple[LearningReviewTicket, ...]:
        """Return the durable ticket projection for diagnostics."""

        return self.ticket_store.tickets()

    @property
    def assessments(self) -> tuple[LearningReviewAssessment, ...]:
        """Return durable candidate-only assessment results."""

        return self.ticket_store.assessments()

    async def publish(self, event: RuntimeLifecycleEvent) -> None:
        """Passively enqueue one configured terminal event, if capacity permits."""

        self.enqueue_terminal_event(event)

    def enqueue_terminal_event(self, event: RuntimeLifecycleEvent) -> LearningReviewTicket | None:
        """Create one idempotent ticket without obtaining mutable runtime objects."""

        if not self.enabled or not _is_reviewable_terminal_event(event):
            return None
        if event.status not in self.allowed_statuses:
            return None
        event_key = _event_key(event)
        return self.ticket_store.enqueue(
            event_key=event_key,
            ticket=LearningReviewTicket(
                ticket_id=_ticket_id(event_key),
                trace_id=event.trace_id,
                plan_ref=event.plan_ref,
                event_status=event.status,
                state_ref=event.state_ref,
                journal_sequence=event.journal_sequence,
            ),
            max_pending=self.max_pending,
        )

    def claim_next(
        self,
        worker_id: str = "learning-review-worker",
        *,
        now: datetime | None = None,
    ) -> LearningReviewTicket | None:
        """Acquire one ticket with an exclusive, time-bounded worker lease."""

        return self.ticket_store.claim_next(
            worker_id,
            now=now or datetime.now(UTC),
            lease_seconds=self.lease_seconds,
        )

    def release(
        self,
        ticket_id: str,
        *,
        lease_id: str | None = None,
        worker_id: str | None = None,
        now: datetime | None = None,
    ) -> LearningReviewTicket:
        """Return the caller-owned claim to the durable queue."""

        ticket = self._require_ticket(ticket_id)
        return self.ticket_store.release(
            ticket_id,
            lease_id=lease_id or _require_lease_id(ticket),
            worker_id=worker_id or _require_lease_worker_id(ticket),
            now=now or datetime.now(UTC),
        )

    def assess_success(
        self,
        ticket_id: str,
        *,
        procedure: str,
        confidence: float,
        evidence_refs: tuple[str, ...],
        lease_id: str | None = None,
        worker_id: str | None = None,
        now: datetime | None = None,
    ) -> LearningReviewAssessment:
        """Ask the candidate service to draft a skill from worker-supplied evidence."""

        ticket = self._require_claimed(ticket_id)
        if ticket.event_status is not TaskStatus.COMPLETED:
            raise ValueError("success assessment requires a completed terminal ticket")
        candidate = self.skill_acquirer.propose(
            task_ref=ticket.trace_id,
            procedure=procedure,
            success=True,
            confidence=confidence,
            evidence_refs=tuple(evidence_refs),
        )
        return self._complete_assessment(
            ticket,
            skill_candidate=candidate,
            lease_id=lease_id,
            worker_id=worker_id,
            now=now,
        )

    def assess_failure(
        self,
        ticket_id: str,
        *,
        trigger: str,
        evidence_refs: tuple[str, ...],
        summary: str = "",
        lease_id: str | None = None,
        worker_id: str | None = None,
        now: datetime | None = None,
    ) -> LearningReviewAssessment:
        """Ask the read-only analyzer to diagnose a failed or partial ticket."""

        ticket = self._require_claimed(ticket_id)
        if ticket.event_status not in {TaskStatus.FAILED, TaskStatus.PARTIAL}:
            raise ValueError("failure assessment requires a failed or partial terminal ticket")
        analysis = self.failure_analyzer.analyze(
            run_ref=ticket.trace_id,
            trigger=trigger,
            evidence_refs=tuple(evidence_refs),
            summary=summary,
        )
        return self._complete_assessment(
            ticket,
            failure_analysis=analysis,
            lease_id=lease_id,
            worker_id=worker_id,
            now=now,
        )

    def _complete_assessment(
        self,
        ticket: LearningReviewTicket,
        *,
        skill_candidate: SkillAcquisitionCandidate | None = None,
        failure_analysis: FailureAnalysis | None = None,
        lease_id: str | None,
        worker_id: str | None,
        now: datetime | None,
    ) -> LearningReviewAssessment:
        assessment = LearningReviewAssessment(
            ticket_id=ticket.ticket_id,
            skill_candidate=skill_candidate,
            failure_analysis=failure_analysis,
        )
        self.ticket_store.complete_assessment(
            assessment,
            lease_id=lease_id or _require_lease_id(ticket),
            worker_id=worker_id or _require_lease_worker_id(ticket),
            now=now or datetime.now(UTC),
        )
        return assessment

    def _require_ticket(self, ticket_id: str) -> LearningReviewTicket:
        for ticket in self.ticket_store.tickets():
            if ticket.ticket_id == ticket_id:
                return ticket
        raise KeyError(f"unknown learning review ticket: {ticket_id!r}")

    def _require_claimed(self, ticket_id: str) -> LearningReviewTicket:
        ticket = self._require_ticket(ticket_id)
        if ticket.status is not LearningReviewTicketStatus.CLAIMED:
            raise ValueError("learning review assessment requires a claimed ticket")
        return ticket


_REVIEWABLE_STATUSES = frozenset(
    {
        TaskStatus.COMPLETED,
        TaskStatus.PARTIAL,
        TaskStatus.FAILED,
    }
)


def _is_reviewable_terminal_event(event: RuntimeLifecycleEvent) -> bool:
    """Reject starts, resumes and phase events before the review queue boundary."""

    expected_status = {
        RuntimeLifecycleEventType.COMPLETED: TaskStatus.COMPLETED,
        RuntimeLifecycleEventType.PARTIAL: TaskStatus.PARTIAL,
        RuntimeLifecycleEventType.FAILED: TaskStatus.FAILED,
    }.get(event.type)
    return expected_status is event.status and event.status in _REVIEWABLE_STATUSES


def _event_key(event: RuntimeLifecycleEvent) -> str:
    """Build the immutable event identity used for repeat-delivery suppression."""

    return "\0".join(
        (
            event.type.value,
            event.trace_id,
            event.plan_ref,
            event.status.value,
            event.state_ref or "",
            str(event.journal_sequence) if event.journal_sequence is not None else "",
        )
    )


def _ticket_id(event_key: str) -> str:
    """Return a deterministic diagnostic id without exposing evidence payloads."""

    digest = sha256(event_key.encode("utf-8")).hexdigest()[:16]
    return f"learning-review-{digest}"


def _require_lease_id(ticket: LearningReviewTicket) -> str:
    if ticket.lease_id is None:
        raise ValueError("learning review ticket has no active lease")
    return ticket.lease_id


def _require_lease_worker_id(ticket: LearningReviewTicket) -> str:
    if ticket.lease_worker_id is None:
        raise ValueError("learning review ticket has no active lease worker")
    return ticket.lease_worker_id


__all__ = [
    "LearningReviewAssessment",
    "LearningReviewService",
    "LearningReviewTicket",
    "LearningReviewTicketStatus",
]
