"""SQLite-backed RunningOperationStore (ADR-0200 I-AGB-5: no status column)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any, Final

from lca.contracts.observability.running_operation import RunningOperationStore

_DEFAULT_PATH: Final[Path] = Path("traces/runtime/lca_running_operations.sqlite3")
_MEMORY_URI = "file:lca_running_operations?mode=memory&cache=shared"

_DDL = """
CREATE TABLE IF NOT EXISTS lca_running_operations (
    run_id                TEXT PRIMARY KEY,
    topic_id              TEXT NOT NULL,
    agent_id              TEXT NOT NULL,
    assistant_message_id  TEXT,
    scope                 TEXT NOT NULL DEFAULT 'main',
    created_at            TEXT NOT NULL DEFAULT (datetime('now')),
    accepted_answer_keys  TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS lca_running_operations_topic_id_idx
    ON lca_running_operations (topic_id, created_at DESC);
"""


class SqliteRunningOperationStore(RunningOperationStore):
    """Process-local SQLite store for gateway reconnect + HIL idempotency."""

    def __init__(self, path: str | Path = _DEFAULT_PATH) -> None:
        self.path = Path(path) if str(path) != ":memory:" else Path(":memory:")
        self._memory = str(path) == ":memory:"
        self._persistent: sqlite3.Connection | None = None
        if not self._memory:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _open_connection(self) -> sqlite3.Connection:
        if self._memory:
            connection = sqlite3.connect(
                _MEMORY_URI,
                uri=True,
                timeout=30.0,
                isolation_level=None,
                check_same_thread=False,
            )
        else:
            connection = sqlite3.connect(
                str(self.path),
                timeout=30.0,
                isolation_level=None,
            )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        if not self._memory:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
        return connection

    @contextmanager
    def _use_connection(self) -> Iterator[sqlite3.Connection]:
        if self._memory:
            yield self._persistent  # type: ignore[misc]
            return
        with closing(self._open_connection()) as connection, connection:
            yield connection

    def _initialize(self) -> None:
        if self._memory:
            self._persistent = self._open_connection()
            self._persistent.executescript(_DDL)
            return
        with closing(self._open_connection()) as connection, connection:
            connection.executescript(_DDL)

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        keys_raw = row["accepted_answer_keys"]
        try:
            accepted = json.loads(keys_raw) if keys_raw else []
        except json.JSONDecodeError:
            accepted = []
        return {
            "run_id": row["run_id"],
            "topic_id": row["topic_id"],
            "agent_id": row["agent_id"],
            "assistant_message_id": row["assistant_message_id"],
            "scope": row["scope"],
            "created_at": row["created_at"],
            "accepted_answer_keys": accepted,
        }

    async def insert(
        self,
        *,
        run_id: str,
        topic_id: str,
        agent_id: str,
        assistant_message_id: str | None,
        scope: str,
    ) -> None:
        with self._use_connection() as connection:
            connection.execute(
                """
                INSERT INTO lca_running_operations
                    (run_id, topic_id, agent_id, assistant_message_id, scope)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO NOTHING
                """,
                (run_id, topic_id, agent_id, assistant_message_id, scope),
            )

    async def get_latest_for_topic(self, topic_id: str) -> dict | None:
        with self._use_connection() as connection:
            row = connection.execute(
                """
                SELECT run_id, topic_id, agent_id, assistant_message_id, scope,
                       created_at, accepted_answer_keys
                FROM lca_running_operations
                WHERE topic_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (topic_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    async def record_answer_key(self, run_id: str, idempotency_key: str) -> None:
        with self._use_connection() as connection:
            row = connection.execute(
                "SELECT accepted_answer_keys FROM lca_running_operations WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                return
            keys: list[str] = []
            try:
                keys = json.loads(row["accepted_answer_keys"] or "[]")
            except json.JSONDecodeError:
                keys = []
            if idempotency_key not in keys:
                keys.append(idempotency_key)
            connection.execute(
                """
                UPDATE lca_running_operations
                SET accepted_answer_keys = ?
                WHERE run_id = ?
                """,
                (json.dumps(keys), run_id),
            )

    async def delete(self, run_id: str) -> None:
        with self._use_connection() as connection:
            connection.execute(
                "DELETE FROM lca_running_operations WHERE run_id = ?",
                (run_id,),
            )

    async def delete_all_for_test(self) -> None:
        """Test helper — wipe all rows."""
        with self._use_connection() as connection:
            connection.execute("DELETE FROM lca_running_operations")


__all__ = ("SqliteRunningOperationStore",)
