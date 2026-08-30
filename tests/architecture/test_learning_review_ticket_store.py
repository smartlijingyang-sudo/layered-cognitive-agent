"""Contract tests for durable candidate-only learning-review ticket storage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.protocols.learning import (
    LearningReviewAssessment,
    LearningReviewTicket,
    LearningReviewTicketStatus,
    SkillAcquisitionCandidate,
)
from lca.infrastructure.learning.review_ticket_sqlite import SqliteLearningReviewTicketStore
from lca.infrastructure.learning.review_ticket_store import LearningReviewTicketLeaseNotOwnedError


def _ticket(ticket_id: str = "ticket-1") -> LearningReviewTicket:
    return LearningReviewTicket(
        ticket_id=ticket_id,
        trace_id=f"trace-{ticket_id}",
        plan_ref="plan://self-improving",
        event_status=TaskStatus.COMPLETED,
        state_ref=f"state://{ticket_id}/4",
        journal_sequence=18,
    )


def _now() -> datetime:
    return datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


def test_sqlite_ticket_store_deduplicates_terminal_event_across_restarts(tmp_path: Path) -> None:
    """One lifecycle fact maps to one durable ticket across store instances."""

    database_path = tmp_path / "learning-review.db"
    first_store = SqliteLearningReviewTicketStore(database_path)
    first = first_store.enqueue(
        event_key="completed\0trace-1",
        ticket=_ticket(),
        max_pending=2,
    )
    assert first is not None

    restarted_store = SqliteLearningReviewTicketStore(database_path)
    duplicate = restarted_store.enqueue(
        event_key="completed\0trace-1",
        ticket=_ticket("ticket-would-be-duplicate"),
        max_pending=2,
    )

    assert duplicate == first
    assert restarted_store.tickets() == (first,)


def test_sqlite_ticket_store_reclaims_expired_lease_and_rejects_stale_owner(tmp_path: Path) -> None:
    """A crashed worker cannot indefinitely block a ticket or settle it later."""

    store = SqliteLearningReviewTicketStore(tmp_path / "learning-review.db")
    assert store.enqueue(event_key="event-1", ticket=_ticket(), max_pending=1) is not None
    first_claim = store.claim_next("worker-a", now=_now(), lease_seconds=10)
    assert first_claim is not None
    assert first_claim.status is LearningReviewTicketStatus.CLAIMED
    assert first_claim.lease_id is not None

    with pytest.raises(LearningReviewTicketLeaseNotOwnedError):
        store.release(
            first_claim.ticket_id,
            lease_id=first_claim.lease_id,
            worker_id="worker-b",
            now=_now(),
        )

    second_claim = store.claim_next(
        "worker-b",
        now=_now() + timedelta(seconds=11),
        lease_seconds=10,
    )
    assert second_claim is not None
    assert second_claim.ticket_id == first_claim.ticket_id
    assert second_claim.lease_id != first_claim.lease_id

    with pytest.raises(LearningReviewTicketLeaseNotOwnedError):
        store.release(
            first_claim.ticket_id,
            lease_id=first_claim.lease_id,
            worker_id="worker-a",
            now=_now() + timedelta(seconds=11),
        )


def test_sqlite_ticket_store_persists_candidate_only_assessment(tmp_path: Path) -> None:
    """Assessment completion survives restart and removes the ticket from reprocessing."""

    database_path = tmp_path / "learning-review.db"
    store = SqliteLearningReviewTicketStore(database_path)
    ticket = _ticket()
    assert store.enqueue(event_key="event-1", ticket=ticket, max_pending=1) is not None
    claimed = store.claim_next("worker-a", now=_now(), lease_seconds=60)
    assert claimed is not None
    assert claimed.lease_id is not None

    assessment = LearningReviewAssessment(
        ticket_id=ticket.ticket_id,
        skill_candidate=SkillAcquisitionCandidate(
            candidate_id="candidate-1",
            task_ref=ticket.trace_id,
            procedure="Validate the capability graph before run execution.",
            confidence=0.9,
            evidence_refs=("journal://18", "state://4", "artifact://summary"),
        ),
    )
    assessed_ticket = store.complete_assessment(
        assessment,
        lease_id=claimed.lease_id,
        worker_id="worker-a",
        now=_now(),
    )

    restarted_store = SqliteLearningReviewTicketStore(database_path)
    assert assessed_ticket.status is LearningReviewTicketStatus.ASSESSED
    assert restarted_store.tickets() == (assessed_ticket,)
    assert restarted_store.assessments() == (assessment,)
    assert restarted_store.claim_next("worker-b", now=_now(), lease_seconds=60) is None
