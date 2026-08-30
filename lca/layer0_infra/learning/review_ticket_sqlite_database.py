"""SQLite connection and schema support for learning-review ticket storage."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class SqliteLearningReviewTicketDatabase:
    """Own the durable database boundary shared by review-ticket operations."""

    def __init__(self, database_path: Path | str) -> None:
        self._database_path = Path(database_path)
        if str(self._database_path) == ":memory:":
            raise ValueError("SqliteLearningReviewTicketStore requires an on-disk database path")
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            self._ensure_schema(connection)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        try:
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

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS learning_review_tickets (
                ticket_id TEXT PRIMARY KEY,
                event_key TEXT NOT NULL UNIQUE,
                trace_id TEXT NOT NULL,
                plan_ref TEXT NOT NULL,
                event_status TEXT NOT NULL,
                state_ref TEXT,
                journal_sequence INTEGER,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                lease_id TEXT,
                lease_worker_id TEXT,
                lease_acquired_at TEXT,
                lease_expires_at TEXT,
                assessment_payload TEXT,
                assessed_at TEXT
            );
            CREATE INDEX IF NOT EXISTS learning_review_ticket_ready_idx
                ON learning_review_tickets (status, lease_expires_at, created_at);
            """
        )


__all__ = ["SqliteLearningReviewTicketDatabase"]
