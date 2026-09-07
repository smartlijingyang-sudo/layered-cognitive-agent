"""RunningOperationStore backends — SQLite (dev) and Postgres (LobeHub stack)."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any, Final

from lca.contracts.observability.running_operation import RunningOperationStore
from lca.infrastructure.persistence.postgres import database_url_from_env, postgres_connection

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


class PostgresRunningOperationStore(RunningOperationStore):
    """Postgres store sharing the LobeHub ``DATABASE_URL`` (spec §3.2)."""

    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url or database_url_from_env()

    def _ensure_schema(self) -> None:
        with postgres_connection(self._database_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS lca_running_operations (
                    run_id                text PRIMARY KEY,
                    topic_id              text NOT NULL,
                    agent_id              text NOT NULL,
                    assistant_message_id  text,
                    scope                 text NOT NULL DEFAULT 'main',
                    created_at            timestamptz NOT NULL DEFAULT now(),
                    accepted_answer_keys  jsonb NOT NULL DEFAULT '[]'::jsonb
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS lca_running_operations_topic_id_idx
                    ON lca_running_operations (topic_id, created_at DESC)
                """
            )
            conn.commit()

    async def insert(
        self,
        *,
        run_id: str,
        topic_id: str,
        agent_id: str,
        assistant_message_id: str | None,
        scope: str,
    ) -> None:
        await asyncio.to_thread(
            self._insert_sync,
            run_id=run_id,
            topic_id=topic_id,
            agent_id=agent_id,
            assistant_message_id=assistant_message_id,
            scope=scope,
        )

    def _insert_sync(
        self,
        *,
        run_id: str,
        topic_id: str,
        agent_id: str,
        assistant_message_id: str | None,
        scope: str,
    ) -> None:
        self._ensure_schema()
        with postgres_connection(self._database_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO lca_running_operations
                    (run_id, topic_id, agent_id, assistant_message_id, scope)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO NOTHING
                """,
                (run_id, topic_id, agent_id, assistant_message_id, scope),
            )
            conn.commit()

    async def get_latest_for_topic(self, topic_id: str) -> dict | None:
        return await asyncio.to_thread(self._get_latest_sync, topic_id)

    def _get_latest_sync(self, topic_id: str) -> dict | None:
        self._ensure_schema()
        with postgres_connection(self._database_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT run_id, topic_id, agent_id, assistant_message_id, scope,
                       created_at, accepted_answer_keys
                FROM lca_running_operations
                WHERE topic_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (topic_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        cols = (
            "run_id",
            "topic_id",
            "agent_id",
            "assistant_message_id",
            "scope",
            "created_at",
            "accepted_answer_keys",
        )
        data = dict(zip(cols, row, strict=True))
        accepted = data.get("accepted_answer_keys")
        if accepted is None:
            data["accepted_answer_keys"] = []
        if hasattr(data["created_at"], "isoformat"):
            data["created_at"] = data["created_at"].isoformat()
        return data

    async def record_answer_key(self, run_id: str, idempotency_key: str) -> None:
        await asyncio.to_thread(self._record_answer_key_sync, run_id, idempotency_key)

    def _record_answer_key_sync(self, run_id: str, idempotency_key: str) -> None:
        self._ensure_schema()
        with postgres_connection(self._database_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE lca_running_operations
                SET accepted_answer_keys = (
                    SELECT COALESCE(jsonb_agg(DISTINCT v), '[]'::jsonb)
                    FROM jsonb_array_elements_text(
                        accepted_answer_keys || to_jsonb(ARRAY[%s]::text[])
                    ) AS v
                )
                WHERE run_id = %s
                """,
                (idempotency_key, run_id),
            )
            conn.commit()

    async def delete(self, run_id: str) -> None:
        await asyncio.to_thread(self._delete_sync, run_id)

    def _delete_sync(self, run_id: str) -> None:
        with postgres_connection(self._database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM lca_running_operations WHERE run_id = %s",
                (run_id,),
            )
            conn.commit()

    async def delete_all_for_test(self) -> None:
        """Test helper; never call from production."""
        await asyncio.to_thread(self._truncate_sync)

    def _truncate_sync(self) -> None:
        self._ensure_schema()
        with postgres_connection(self._database_url) as conn, conn.cursor() as cur:
            cur.execute("TRUNCATE lca_running_operations")
            conn.commit()


def resolve_running_operation_store() -> RunningOperationStore:
    """Prefer Postgres when ``DATABASE_URL`` connects; else process-local SQLite."""
    from lca.infrastructure.persistence.postgres import postgres_available

    if postgres_available():
        return PostgresRunningOperationStore()
    return SqliteRunningOperationStore()


__all__ = (
    "PostgresRunningOperationStore",
    "SqliteRunningOperationStore",
    "resolve_running_operation_store",
)
