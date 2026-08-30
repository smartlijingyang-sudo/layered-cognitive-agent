"""SQLite persistence and lease ownership for continuous work items."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from lca.contracts.harness.tasks.continuous import (
    WorkActivationReceipt,
    WorkItem,
    WorkLease,
    WorkQueue,
    WorkStatus,
)
from lca.harness.continuous_serialization import (
    max_attempts_from_payload,
    require_aware,
    timestamp,
    work_item_from_payload,
    work_item_payload,
)


class LeaseNotOwnedError(RuntimeError):
    """Raised when an acknowledgement cannot prove exclusive lease ownership."""


class SqliteWorkQueue(WorkQueue):
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS continuous_work_items (
                    work_id TEXT PRIMARY KEY,
                    trigger_id TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    available_at TEXT NOT NULL,
                    lease_id TEXT,
                    lease_worker_id TEXT,
                    lease_acquired_at TEXT,
                    lease_expires_at TEXT,
                    session_id TEXT,
                    detail TEXT NOT NULL DEFAULT '',
                    dispatched_at TEXT
                );
                CREATE INDEX IF NOT EXISTS continuous_work_ready_idx
                    ON continuous_work_items (status, available_at, lease_expires_at);
                """
            )

    def submit(self, item: WorkItem) -> WorkItem:
        available_at = item.available_at or item.trigger.occurred_at
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT payload FROM continuous_work_items WHERE work_id = ? OR trigger_id = ?",
                (item.work_id, item.trigger.trigger_id),
            ).fetchone()
            if existing is not None:
                return work_item_from_payload(existing[0])
            connection.execute(
                """
                INSERT INTO continuous_work_items (
                    work_id, trigger_id, payload, status, available_at, session_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item.work_id,
                    item.trigger.trigger_id,
                    work_item_payload(item),
                    WorkStatus.PENDING.value,
                    timestamp(available_at),
                    item.session_id,
                ),
            )
        return item

    def get(self, work_id: str) -> WorkItem | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload FROM continuous_work_items WHERE work_id = ?", (work_id,)
            ).fetchone()
        return work_item_from_payload(row[0]) if row is not None else None

    def status_of(self, work_id: str) -> WorkStatus | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT status FROM continuous_work_items WHERE work_id = ?", (work_id,)
            ).fetchone()
        return WorkStatus(row[0]) if row is not None else None

    def claim(self, worker_id: str, *, now: datetime, lease_seconds: int) -> WorkLease | None:
        if not worker_id.strip():
            raise ValueError("worker_id must not be empty")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        now = require_aware(now)
        expires_at = now + timedelta(seconds=lease_seconds)
        with self._transaction() as connection:
            connection.execute(
                """
                UPDATE continuous_work_items
                SET status = ?, lease_id = NULL, lease_worker_id = NULL,
                    lease_acquired_at = NULL, lease_expires_at = NULL,
                    detail = 'lease_expired'
                WHERE status = ? AND lease_expires_at <= ? AND attempts >= max_attempts_from_payload(payload)
                """,
                (WorkStatus.DEAD.value, WorkStatus.LEASED.value, timestamp(now)),
            )
            row = connection.execute(
                """
                SELECT work_id, payload, attempts
                FROM continuous_work_items
                WHERE (
                    (status IN (?, ?) AND available_at <= ?)
                    OR (status = ? AND lease_expires_at <= ?)
                )
                AND attempts < max_attempts_from_payload(payload)
                ORDER BY available_at, work_id
                LIMIT 1
                """,
                (
                    WorkStatus.PENDING.value,
                    WorkStatus.RETRY_WAIT.value,
                    timestamp(now),
                    WorkStatus.LEASED.value,
                    timestamp(now),
                ),
            ).fetchone()
            if row is None:
                return None
            lease = WorkLease(
                work_id=row[0],
                lease_id=f"lease-{uuid4().hex}",
                worker_id=worker_id,
                acquired_at=now,
                expires_at=expires_at,
                attempt=int(row[2]) + 1,
            )
            connection.execute(
                """
                UPDATE continuous_work_items
                SET status = ?, attempts = ?, lease_id = ?, lease_worker_id = ?,
                    lease_acquired_at = ?, lease_expires_at = ?, detail = ''
                WHERE work_id = ?
                """,
                (
                    WorkStatus.LEASED.value,
                    lease.attempt,
                    lease.lease_id,
                    lease.worker_id,
                    timestamp(lease.acquired_at),
                    timestamp(lease.expires_at),
                    lease.work_id,
                ),
            )
        return lease

    def acknowledge(self, lease: WorkLease, receipt: WorkActivationReceipt) -> None:
        if not receipt.accepted:
            raise ValueError("only accepted activations may be acknowledged")
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE continuous_work_items
                SET status = ?, session_id = COALESCE(?, session_id),
                    dispatched_at = ?, detail = ?, lease_id = NULL,
                    lease_worker_id = NULL, lease_acquired_at = NULL, lease_expires_at = NULL
                WHERE work_id = ? AND status = ? AND lease_id = ? AND lease_worker_id = ?
                """,
                (
                    WorkStatus.DISPATCHED.value,
                    receipt.session_id,
                    timestamp(datetime.now(UTC)),
                    receipt.detail,
                    lease.work_id,
                    WorkStatus.LEASED.value,
                    lease.lease_id,
                    lease.worker_id,
                ),
            )
            if cursor.rowcount != 1:
                raise LeaseNotOwnedError(f"cannot acknowledge work item {lease.work_id!r}")

    def release(
        self,
        lease: WorkLease,
        *,
        now: datetime,
        retry_delay_seconds: float,
        detail: str,
    ) -> WorkStatus:
        now = require_aware(now)
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must be non-negative")
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT payload, attempts FROM continuous_work_items
                WHERE work_id = ? AND status = ? AND lease_id = ? AND lease_worker_id = ?
                """,
                (lease.work_id, WorkStatus.LEASED.value, lease.lease_id, lease.worker_id),
            ).fetchone()
            if row is None:
                raise LeaseNotOwnedError(f"cannot release work item {lease.work_id!r}")
            item = work_item_from_payload(row[0])
            status = WorkStatus.DEAD if int(row[1]) >= item.max_attempts else WorkStatus.RETRY_WAIT
            available_at = now + timedelta(seconds=retry_delay_seconds)
            connection.execute(
                """
                UPDATE continuous_work_items
                SET status = ?, available_at = ?, detail = ?, lease_id = NULL,
                    lease_worker_id = NULL, lease_acquired_at = NULL, lease_expires_at = NULL
                WHERE work_id = ?
                """,
                (status.value, timestamp(available_at), detail, lease.work_id),
            )
        return status

    def cancel(self, work_id: str) -> bool:
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE continuous_work_items SET status = ?, detail = 'canceled'
                WHERE work_id = ? AND status IN (?, ?)
                """,
                (
                    WorkStatus.CANCELED.value,
                    work_id,
                    WorkStatus.PENDING.value,
                    WorkStatus.RETRY_WAIT.value,
                ),
            )
        return cursor.rowcount == 1

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path)
        try:
            connection.create_function("max_attempts_from_payload", 1, max_attempts_from_payload)
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()


__all__ = ["LeaseNotOwnedError", "SqliteWorkQueue"]
