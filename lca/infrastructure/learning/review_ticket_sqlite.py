"""SQLite WAL-backed storage for candidate-only learning-review tickets."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from lca.contracts.protocols.think.learning import (
    LearningReviewAssessment,
    LearningReviewTicket,
    LearningReviewTicketStatus,
    LearningReviewTicketStore,
)
from lca.infrastructure.learning.review_ticket_serialization import (
    assessment_from_payload,
    assessment_payload,
    ticket_from_row,
    timestamp,
    validate_claim,
    validate_enqueue,
    validate_settlement_time,
)
from lca.infrastructure.learning.review_ticket_sqlite_database import (
    SqliteLearningReviewTicketDatabase,
)
from lca.infrastructure.learning.review_ticket_store import LearningReviewTicketLeaseNotOwnedError


class SqliteLearningReviewTicketStore(
    SqliteLearningReviewTicketDatabase,
    LearningReviewTicketStore,
):
    """Persist idempotent terminal tickets and lease-verified assessments in SQLite."""

    def enqueue(
        self,
        *,
        event_key: str,
        ticket: LearningReviewTicket,
        max_pending: int,
    ) -> LearningReviewTicket | None:
        validate_enqueue(event_key=event_key, ticket=ticket, max_pending=max_pending)
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM learning_review_tickets WHERE event_key = ?",
                (event_key,),
            ).fetchone()
            if existing is not None:
                return ticket_from_row(existing)
            pending_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM learning_review_tickets WHERE status != ?",
                    (LearningReviewTicketStatus.ASSESSED.value,),
                ).fetchone()[0]
            )
            if pending_count >= max_pending:
                return None
            connection.execute(
                """
                INSERT INTO learning_review_tickets (
                    ticket_id, event_key, trace_id, plan_ref, event_status, state_ref,
                    journal_sequence, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ticket.ticket_id,
                    event_key,
                    ticket.trace_id,
                    ticket.plan_ref,
                    ticket.event_status.value,
                    ticket.state_ref,
                    ticket.journal_sequence,
                    LearningReviewTicketStatus.QUEUED.value,
                    timestamp(datetime.now(UTC)),
                ),
            )
            row = connection.execute(
                "SELECT * FROM learning_review_tickets WHERE ticket_id = ?",
                (ticket.ticket_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("learning review ticket insert did not produce a row")
        return ticket_from_row(row)

    def tickets(self) -> tuple[LearningReviewTicket, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM learning_review_tickets ORDER BY created_at, ticket_id"
            ).fetchall()
        return tuple(ticket_from_row(row) for row in rows)

    def assessments(self) -> tuple[LearningReviewAssessment, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT assessment_payload FROM learning_review_tickets
                WHERE assessment_payload IS NOT NULL
                ORDER BY assessed_at, ticket_id
                """
            ).fetchall()
        return tuple(assessment_from_payload(str(row[0])) for row in rows)

    def claim_next(
        self,
        worker_id: str,
        *,
        now: datetime,
        lease_seconds: int,
    ) -> LearningReviewTicket | None:
        validate_claim(worker_id=worker_id, now=now, lease_seconds=lease_seconds)
        expires_at = now + timedelta(seconds=lease_seconds)
        with self._transaction() as connection:
            connection.execute(
                """
                UPDATE learning_review_tickets
                SET status = ?, lease_id = NULL, lease_worker_id = NULL,
                    lease_acquired_at = NULL, lease_expires_at = NULL
                WHERE status = ? AND lease_expires_at <= ?
                """,
                (
                    LearningReviewTicketStatus.QUEUED.value,
                    LearningReviewTicketStatus.CLAIMED.value,
                    timestamp(now),
                ),
            )
            row = connection.execute(
                """
                SELECT ticket_id FROM learning_review_tickets
                WHERE status = ?
                ORDER BY created_at, ticket_id
                LIMIT 1
                """,
                (LearningReviewTicketStatus.QUEUED.value,),
            ).fetchone()
            if row is None:
                return None
            ticket_id = str(row[0])
            lease_id = f"learning-review-lease-{uuid4().hex}"
            connection.execute(
                """
                UPDATE learning_review_tickets
                SET status = ?, lease_id = ?, lease_worker_id = ?,
                    lease_acquired_at = ?, lease_expires_at = ?
                WHERE ticket_id = ?
                """,
                (
                    LearningReviewTicketStatus.CLAIMED.value,
                    lease_id,
                    worker_id,
                    timestamp(now),
                    timestamp(expires_at),
                    ticket_id,
                ),
            )
            claimed = connection.execute(
                "SELECT * FROM learning_review_tickets WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchone()
        if claimed is None:
            raise RuntimeError("learning review ticket claim did not produce a row")
        return ticket_from_row(claimed)

    def release(
        self,
        ticket_id: str,
        *,
        lease_id: str,
        worker_id: str,
        now: datetime,
    ) -> LearningReviewTicket:
        self._validate_lease_inputs(ticket_id, lease_id=lease_id, worker_id=worker_id, now=now)
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE learning_review_tickets
                SET status = ?, lease_id = NULL, lease_worker_id = NULL,
                    lease_acquired_at = NULL, lease_expires_at = NULL
                WHERE ticket_id = ? AND status = ? AND lease_id = ? AND lease_worker_id = ?
                    AND lease_expires_at > ?
                """,
                (
                    LearningReviewTicketStatus.QUEUED.value,
                    ticket_id,
                    LearningReviewTicketStatus.CLAIMED.value,
                    lease_id,
                    worker_id,
                    timestamp(now),
                ),
            )
            if cursor.rowcount != 1:
                raise LearningReviewTicketLeaseNotOwnedError(
                    f"worker does not own learning review ticket {ticket_id!r}"
                )
            row = connection.execute(
                "SELECT * FROM learning_review_tickets WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("learning review ticket release did not produce a row")
        return ticket_from_row(row)

    def complete_assessment(
        self,
        assessment: LearningReviewAssessment,
        *,
        lease_id: str,
        worker_id: str,
        now: datetime,
    ) -> LearningReviewTicket:
        self._validate_lease_inputs(
            assessment.ticket_id,
            lease_id=lease_id,
            worker_id=worker_id,
            now=now,
        )
        payload = assessment_payload(assessment)
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE learning_review_tickets
                SET status = ?, assessment_payload = ?, assessed_at = ?,
                    lease_id = NULL, lease_worker_id = NULL,
                    lease_acquired_at = NULL, lease_expires_at = NULL
                WHERE ticket_id = ? AND status = ? AND lease_id = ? AND lease_worker_id = ?
                    AND lease_expires_at > ?
                """,
                (
                    LearningReviewTicketStatus.ASSESSED.value,
                    payload,
                    timestamp(now),
                    assessment.ticket_id,
                    LearningReviewTicketStatus.CLAIMED.value,
                    lease_id,
                    worker_id,
                    timestamp(now),
                ),
            )
            if cursor.rowcount != 1:
                raise LearningReviewTicketLeaseNotOwnedError(
                    f"worker does not own learning review ticket {assessment.ticket_id!r}"
                )
            row = connection.execute(
                "SELECT * FROM learning_review_tickets WHERE ticket_id = ?",
                (assessment.ticket_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("learning review assessment did not produce a ticket row")
        return ticket_from_row(row)

    @staticmethod
    def _validate_lease_inputs(
        ticket_id: str,
        *,
        lease_id: str,
        worker_id: str,
        now: datetime,
    ) -> None:
        if not ticket_id.strip() or not lease_id.strip() or not worker_id.strip():
            raise ValueError("ticket_id, lease_id, and worker_id must not be empty")
        validate_settlement_time(now)


__all__ = ["SqliteLearningReviewTicketStore"]
