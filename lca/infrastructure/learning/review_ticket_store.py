"""In-memory storage for candidate-only learning-review tickets.

The in-memory provider is intentionally limited to tests and ephemeral profiles.
The durable SQLite implementation is isolated in ``review_ticket_sqlite``.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from lca.contracts.protocols.think.learning import (
    LearningReviewAssessment,
    LearningReviewTicket,
    LearningReviewTicketStatus,
    LearningReviewTicketStore,
)
from lca.infrastructure.learning.review_ticket_serialization import (
    claimed_ticket,
    is_owned_claim,
    queued_ticket,
    validate_claim,
    validate_enqueue,
    validate_settlement_time,
)


class LearningReviewTicketLeaseNotOwnedError(RuntimeError):
    """Raised when a worker cannot prove ownership of a review-ticket lease."""


class InMemoryLearningReviewTicketStore(LearningReviewTicketStore):
    """Deterministic in-memory store for focused tests and ephemeral profiles."""

    def __init__(self) -> None:
        self._tickets: dict[str, LearningReviewTicket] = {}
        self._event_ticket_ids: dict[str, str] = {}
        self._assessments: dict[str, LearningReviewAssessment] = {}

    def enqueue(
        self,
        *,
        event_key: str,
        ticket: LearningReviewTicket,
        max_pending: int,
    ) -> LearningReviewTicket | None:
        validate_enqueue(event_key=event_key, ticket=ticket, max_pending=max_pending)
        existing_id = self._event_ticket_ids.get(event_key)
        if existing_id is not None:
            return self._tickets[existing_id]
        if self._pending_count() >= max_pending:
            return None
        self._event_ticket_ids[event_key] = ticket.ticket_id
        self._tickets[ticket.ticket_id] = ticket
        return ticket

    def tickets(self) -> tuple[LearningReviewTicket, ...]:
        return tuple(self._tickets.values())

    def assessments(self) -> tuple[LearningReviewAssessment, ...]:
        return tuple(self._assessments.values())

    def claim_next(
        self,
        worker_id: str,
        *,
        now: datetime,
        lease_seconds: int,
    ) -> LearningReviewTicket | None:
        validate_claim(worker_id=worker_id, now=now, lease_seconds=lease_seconds)
        for ticket_id, ticket in self._tickets.items():
            if (
                ticket.status is LearningReviewTicketStatus.CLAIMED
                and ticket.lease_expires_at is not None
                and ticket.lease_expires_at <= now
            ):
                self._tickets[ticket_id] = queued_ticket(ticket)
        for ticket_id, ticket in self._tickets.items():
            if ticket.status is not LearningReviewTicketStatus.QUEUED:
                continue
            claimed = claimed_ticket(
                ticket,
                worker_id=worker_id,
                now=now,
                lease_seconds=lease_seconds,
            )
            self._tickets[ticket_id] = claimed
            return claimed
        return None

    def release(
        self,
        ticket_id: str,
        *,
        lease_id: str,
        worker_id: str,
        now: datetime,
    ) -> LearningReviewTicket:
        ticket = self._require_owned_claim(
            ticket_id,
            lease_id=lease_id,
            worker_id=worker_id,
            now=now,
        )
        queued = queued_ticket(ticket)
        self._tickets[ticket_id] = queued
        return queued

    def complete_assessment(
        self,
        assessment: LearningReviewAssessment,
        *,
        lease_id: str,
        worker_id: str,
        now: datetime,
    ) -> LearningReviewTicket:
        ticket = self._require_owned_claim(
            assessment.ticket_id,
            lease_id=lease_id,
            worker_id=worker_id,
            now=now,
        )
        assessed = replace(
            ticket,
            status=LearningReviewTicketStatus.ASSESSED,
            lease_id=None,
            lease_worker_id=None,
            lease_acquired_at=None,
            lease_expires_at=None,
        )
        self._tickets[assessment.ticket_id] = assessed
        self._assessments[assessment.ticket_id] = assessment
        return assessed

    def _pending_count(self) -> int:
        return sum(
            ticket.status is not LearningReviewTicketStatus.ASSESSED
            for ticket in self._tickets.values()
        )

    def _require_owned_claim(
        self,
        ticket_id: str,
        *,
        lease_id: str,
        worker_id: str,
        now: datetime,
    ) -> LearningReviewTicket:
        validate_settlement_time(now)
        try:
            ticket = self._tickets[ticket_id]
        except KeyError as error:
            raise KeyError(f"unknown learning review ticket: {ticket_id!r}") from error
        if not is_owned_claim(ticket, lease_id=lease_id, worker_id=worker_id, now=now):
            raise LearningReviewTicketLeaseNotOwnedError(
                f"worker does not own learning review ticket {ticket_id!r}"
            )
        return ticket


__all__ = ["InMemoryLearningReviewTicketStore", "LearningReviewTicketLeaseNotOwnedError"]
