"""Serialization and lease helpers for learning-review ticket storage."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.protocols.think.learning import (
    FailureAnalysis,
    LearningReviewAssessment,
    LearningReviewTicket,
    LearningReviewTicketStatus,
    SkillAcquisitionCandidate,
)


def validate_enqueue(
    *,
    event_key: str,
    ticket: LearningReviewTicket,
    max_pending: int,
) -> None:
    """Reject malformed new tickets before a store performs an atomic insert."""

    if not event_key.strip():
        raise ValueError("learning review event_key must not be empty")
    if not ticket.ticket_id.strip():
        raise ValueError("learning review ticket_id must not be empty")
    if ticket.status is not LearningReviewTicketStatus.QUEUED:
        raise ValueError("only queued learning review tickets may be enqueued")
    if any(
        value is not None
        for value in (
            ticket.lease_id,
            ticket.lease_worker_id,
            ticket.lease_acquired_at,
            ticket.lease_expires_at,
        )
    ):
        raise ValueError("new learning review tickets must not carry a lease")
    if max_pending <= 0:
        raise ValueError("learning review max_pending must be positive")


def validate_claim(*, worker_id: str, now: datetime, lease_seconds: int) -> None:
    """Validate the explicit time and identity used to acquire a ticket."""

    if not worker_id.strip():
        raise ValueError("learning review worker_id must not be empty")
    if now.tzinfo is None:
        raise ValueError("learning review claim time must be timezone-aware")
    if lease_seconds <= 0:
        raise ValueError("learning review lease_seconds must be positive")


def validate_settlement_time(now: datetime) -> None:
    """Reject naïve settlement timestamps that make expiry comparison ambiguous."""

    if now.tzinfo is None:
        raise ValueError("learning review settlement time must be timezone-aware")


def claimed_ticket(
    ticket: LearningReviewTicket,
    *,
    worker_id: str,
    now: datetime,
    lease_seconds: int,
) -> LearningReviewTicket:
    """Return a ticket with a new exclusive, time-bounded lease."""

    return replace(
        ticket,
        status=LearningReviewTicketStatus.CLAIMED,
        lease_id=f"learning-review-lease-{uuid4().hex}",
        lease_worker_id=worker_id,
        lease_acquired_at=now,
        lease_expires_at=now + timedelta(seconds=lease_seconds),
    )


def queued_ticket(ticket: LearningReviewTicket) -> LearningReviewTicket:
    """Clear a lease while returning a ticket to its pending durable state."""

    return replace(
        ticket,
        status=LearningReviewTicketStatus.QUEUED,
        lease_id=None,
        lease_worker_id=None,
        lease_acquired_at=None,
        lease_expires_at=None,
    )


def is_owned_claim(
    ticket: LearningReviewTicket,
    *,
    lease_id: str,
    worker_id: str,
    now: datetime,
) -> bool:
    """Return whether a worker can settle this unexpired ticket lease."""

    return (
        ticket.status is LearningReviewTicketStatus.CLAIMED
        and ticket.lease_id == lease_id
        and ticket.lease_worker_id == worker_id
        and ticket.lease_expires_at is not None
        and ticket.lease_expires_at > now
    )


def timestamp(value: datetime) -> str:
    """Return a canonical UTC representation suitable for SQLite comparisons."""

    if value.tzinfo is None:
        raise ValueError("learning review timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def datetime_from_storage(value: str | None) -> datetime | None:
    """Parse an aware timestamp stored by :func:`timestamp`."""

    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("stored learning review timestamp must be timezone-aware")
    return parsed


def ticket_from_row(row: sqlite3.Row) -> LearningReviewTicket:
    """Project a SQLite ticket row into the immutable contract value."""

    return LearningReviewTicket(
        ticket_id=str(row["ticket_id"]),
        trace_id=str(row["trace_id"]),
        plan_ref=str(row["plan_ref"]),
        event_status=TaskStatus(str(row["event_status"])),
        state_ref=str(row["state_ref"]) if row["state_ref"] is not None else None,
        journal_sequence=int(row["journal_sequence"])
        if row["journal_sequence"] is not None
        else None,
        status=LearningReviewTicketStatus(str(row["status"])),
        lease_id=str(row["lease_id"]) if row["lease_id"] is not None else None,
        lease_worker_id=(
            str(row["lease_worker_id"]) if row["lease_worker_id"] is not None else None
        ),
        lease_acquired_at=datetime_from_storage(row["lease_acquired_at"]),
        lease_expires_at=datetime_from_storage(row["lease_expires_at"]),
    )


def assessment_payload(assessment: LearningReviewAssessment) -> str:
    """Encode a candidate-only assessment in deterministic JSON."""

    candidate = assessment.skill_candidate
    analysis = assessment.failure_analysis
    if candidate is not None and analysis is not None:
        raise ValueError("learning review assessment must contain only one outcome")
    return json.dumps(
        {
            "ticket_id": assessment.ticket_id,
            "skill_candidate": (
                {
                    "candidate_id": candidate.candidate_id,
                    "task_ref": candidate.task_ref,
                    "procedure": candidate.procedure,
                    "confidence": candidate.confidence,
                    "evidence_refs": list(candidate.evidence_refs),
                    "status": candidate.status,
                }
                if candidate is not None
                else None
            ),
            "failure_analysis": (
                {
                    "run_ref": analysis.run_ref,
                    "trigger": analysis.trigger,
                    "root_cause": analysis.root_cause,
                    "evidence_refs": list(analysis.evidence_refs),
                    "suggestions": list(analysis.suggestions),
                }
                if analysis is not None
                else None
            ),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def assessment_from_payload(payload: str) -> LearningReviewAssessment:
    """Decode an assessment persisted by :func:`assessment_payload`."""

    data = json.loads(payload)
    candidate_data = data.get("skill_candidate")
    analysis_data = data.get("failure_analysis")
    candidate = (
        SkillAcquisitionCandidate(
            candidate_id=str(candidate_data["candidate_id"]),
            task_ref=str(candidate_data["task_ref"]),
            procedure=str(candidate_data["procedure"]),
            confidence=float(candidate_data["confidence"]),
            evidence_refs=tuple(str(item) for item in candidate_data["evidence_refs"]),
            status=str(candidate_data["status"]),
        )
        if isinstance(candidate_data, dict)
        else None
    )
    analysis = (
        FailureAnalysis(
            run_ref=str(analysis_data["run_ref"]),
            trigger=str(analysis_data["trigger"]),
            root_cause=str(analysis_data["root_cause"]),
            evidence_refs=tuple(str(item) for item in analysis_data["evidence_refs"]),
            suggestions=tuple(str(item) for item in analysis_data["suggestions"]),
        )
        if isinstance(analysis_data, dict)
        else None
    )
    return LearningReviewAssessment(
        ticket_id=str(data["ticket_id"]),
        skill_candidate=candidate,
        failure_analysis=analysis,
    )


__all__ = [
    "assessment_from_payload",
    "assessment_payload",
    "claimed_ticket",
    "datetime_from_storage",
    "is_owned_claim",
    "queued_ticket",
    "ticket_from_row",
    "timestamp",
    "validate_claim",
    "validate_enqueue",
    "validate_settlement_time",
]
