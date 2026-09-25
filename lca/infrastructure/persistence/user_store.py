"""UserAssistantStore —— LCA 自有数据库（ADR-0252 D2/D3）。

双后端模式（仿 ``RunningOperationStore``）：

- ``SqliteUserAssistantStore`` —— 开发/默认，落 ``~/.lca/lca.sqlite3``（WAL）；
- ``PostgresUserAssistantStore`` —— 生产，独立 Postgres 库经
  ``LCA_DATABASE_URL`` 注入（不是 LobeHub 的 ``lobechat`` 库）。

两类均实现 :class:`AssistantOwnership`。方法为同步实现（调用点与
``assistant.catalog`` 一致），事务语义由各连接管理。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lca.contracts.protocols.assistant.ownership import (
    AssistantOwnership,
    UserAssistantBinding,
)
from lca.infrastructure.persistence.postgres import postgres_connection

_DEFAULT_PATH: Path = Path("~/.lca/lca.sqlite3").expanduser()

_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS lca_users (
    user_id          TEXT PRIMARY KEY,
    username         TEXT,
    email            TEXT,
    onboarding_state TEXT NOT NULL DEFAULT 'pending',
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS lca_user_assistants (
    user_id        TEXT NOT NULL REFERENCES lca_users(user_id) ON DELETE CASCADE,
    assistant_id   TEXT PRIMARY KEY,
    client_id      TEXT NOT NULL,
    role_id        TEXT,
    initial_skills TEXT NOT NULL DEFAULT '[]',
    agent_id       TEXT,
    status         TEXT NOT NULL DEFAULT 'pending',
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, client_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS lca_user_assistants_agent_idx
    ON lca_user_assistants (agent_id) WHERE agent_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS lca_user_assistants_user_id_idx
    ON lca_user_assistants (user_id);
"""

_POSTGRES_DDL = """
CREATE TABLE IF NOT EXISTS lca_users (
    user_id          text PRIMARY KEY,
    username         text,
    email            text,
    onboarding_state text NOT NULL DEFAULT 'pending',
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS lca_user_assistants (
    user_id        text NOT NULL REFERENCES lca_users(user_id) ON DELETE CASCADE,
    assistant_id   text PRIMARY KEY,
    client_id      text NOT NULL,
    role_id        text,
    initial_skills jsonb NOT NULL DEFAULT '[]'::jsonb,
    agent_id       text,
    status         text NOT NULL DEFAULT 'pending',
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, client_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS lca_user_assistants_agent_idx
    ON lca_user_assistants (agent_id) WHERE agent_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS lca_user_assistants_user_id_idx
    ON lca_user_assistants (user_id);
"""


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class SqliteUserAssistantStore(AssistantOwnership):
    """SQLite 实现（开发默认）。"""

    def __init__(self, path: str | Path = _DEFAULT_PATH) -> None:
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _open_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self.path),
            timeout=30.0,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        if str(self.path) != ":memory:":
            connection.execute("PRAGMA journal_mode=WAL")
        return connection

    @contextmanager
    def _use_connection(self) -> Iterator[sqlite3.Connection]:
        with closing(self._open_connection()) as connection, connection:
            yield connection

    def _initialize(self) -> None:
        with self._use_connection() as connection:
            connection.executescript(_SQLITE_DDL)

    # ── AssistantOwnership ──────────────────────────────────────────

    def ensure_user(
        self,
        user_id: str,
        *,
        username: str | None = None,
        email: str | None = None,
    ) -> None:
        with self._use_connection() as connection:
            connection.execute(
                """
                INSERT INTO lca_users (user_id, username, email)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = COALESCE(excluded.username, lca_users.username),
                    email = COALESCE(excluded.email, lca_users.email),
                    updated_at = datetime('now')
                """,
                (user_id, username, email),
            )

    def bind(self, binding: UserAssistantBinding) -> None:
        with self._use_connection() as connection:
            existing = connection.execute(
                "SELECT assistant_id FROM lca_user_assistants WHERE user_id = ? AND client_id = ?",
                (binding.user_id, binding.client_id),
            ).fetchone()
            if existing is not None:
                return
            connection.execute(
                """
                INSERT INTO lca_user_assistants
                    (user_id, assistant_id, client_id, role_id, initial_skills, agent_id, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(assistant_id) DO NOTHING
                """,
                (
                    binding.user_id,
                    binding.assistant_id,
                    binding.client_id,
                    binding.role_id,
                    json.dumps(list(binding.initial_skills)),
                    binding.agent_id,
                    binding.status,
                ),
            )

    def owner_of(self, assistant_id: str) -> str | None:
        with self._use_connection() as connection:
            row = connection.execute(
                "SELECT user_id FROM lca_user_assistants WHERE assistant_id = ?",
                (assistant_id,),
            ).fetchone()
        return str(row["user_id"]) if row is not None else None

    def assistant_id_for_client(self, user_id: str, client_id: str) -> str | None:
        with self._use_connection() as connection:
            row = connection.execute(
                "SELECT assistant_id FROM lca_user_assistants WHERE user_id = ? AND client_id = ?",
                (user_id, client_id),
            ).fetchone()
        return str(row["assistant_id"]) if row is not None else None

    def assistant_ids_for(self, user_id: str) -> tuple[str, ...]:
        with self._use_connection() as connection:
            rows = connection.execute(
                "SELECT assistant_id FROM lca_user_assistants WHERE user_id = ? ORDER BY created_at",
                (user_id,),
            ).fetchall()
        return tuple(str(row["assistant_id"]) for row in rows)

    def set_agent_id(self, assistant_id: str, agent_id: str) -> None:
        with self._use_connection() as connection:
            connection.execute(
                """
                UPDATE lca_user_assistants
                SET agent_id = ?, status = 'active'
                WHERE assistant_id = ?
                """,
                (agent_id, assistant_id),
            )

    def agent_id_of(self, assistant_id: str) -> str | None:
        with self._use_connection() as connection:
            row = connection.execute(
                "SELECT agent_id FROM lca_user_assistants WHERE assistant_id = ?",
                (assistant_id,),
            ).fetchone()
        if row is None or row["agent_id"] is None:
            return None
        return str(row["agent_id"])

    def set_onboarding_state(self, user_id: str, state: str) -> None:
        with self._use_connection() as connection:
            connection.execute(
                """
                UPDATE lca_users
                SET onboarding_state = ?, updated_at = datetime('now')
                WHERE user_id = ?
                """,
                (state, user_id),
            )

    def get_onboarding_state(self, user_id: str) -> str:
        with self._use_connection() as connection:
            row = connection.execute(
                "SELECT onboarding_state FROM lca_users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return str(row["onboarding_state"]) if row is not None else "pending"


class PostgresUserAssistantStore(AssistantOwnership):
    """Postgres 实现（生产，独立 ``lca`` 库）。"""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._initialize()

    def _initialize(self) -> None:
        with postgres_connection(self._database_url) as conn, conn.cursor() as cur:
            cur.execute(_POSTGRES_DDL)
            conn.commit()

    def _use_cursor(self, fn: Any) -> Any:
        with postgres_connection(self._database_url) as conn, conn.cursor() as cur:
            result = fn(cur)
            conn.commit()
            return result

    # ── AssistantOwnership ──────────────────────────────────────────

    def ensure_user(
        self,
        user_id: str,
        *,
        username: str | None = None,
        email: str | None = None,
    ) -> None:
        def _run(cur: Any) -> None:
            cur.execute(
                """
                INSERT INTO lca_users (user_id, username, email)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    username = COALESCE(EXCLUDED.username, lca_users.username),
                    email = COALESCE(EXCLUDED.email, lca_users.email),
                    updated_at = now()
                """,
                (user_id, username, email),
            )

        self._use_cursor(_run)

    def bind(self, binding: UserAssistantBinding) -> None:
        def _run(cur: Any) -> None:
            cur.execute(
                "SELECT assistant_id FROM lca_user_assistants WHERE user_id = %s AND client_id = %s",
                (binding.user_id, binding.client_id),
            )
            if cur.fetchone() is not None:
                return
            cur.execute(
                """
                INSERT INTO lca_user_assistants
                    (user_id, assistant_id, client_id, role_id, initial_skills, agent_id, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (assistant_id) DO NOTHING
                """,
                (
                    binding.user_id,
                    binding.assistant_id,
                    binding.client_id,
                    binding.role_id,
                    json.dumps(list(binding.initial_skills)),
                    binding.agent_id,
                    binding.status,
                ),
            )

        self._use_cursor(_run)

    def owner_of(self, assistant_id: str) -> str | None:
        def _run(cur: Any) -> str | None:
            cur.execute(
                "SELECT user_id FROM lca_user_assistants WHERE assistant_id = %s",
                (assistant_id,),
            )
            row = cur.fetchone()
            return str(row[0]) if row is not None else None

        return self._use_cursor(_run)

    def assistant_id_for_client(self, user_id: str, client_id: str) -> str | None:
        def _run(cur: Any) -> str | None:
            cur.execute(
                "SELECT assistant_id FROM lca_user_assistants WHERE user_id = %s AND client_id = %s",
                (user_id, client_id),
            )
            row = cur.fetchone()
            return str(row[0]) if row is not None else None

        return self._use_cursor(_run)

    def assistant_ids_for(self, user_id: str) -> tuple[str, ...]:
        def _run(cur: Any) -> tuple[str, ...]:
            cur.execute(
                "SELECT assistant_id FROM lca_user_assistants WHERE user_id = %s ORDER BY created_at",
                (user_id,),
            )
            return tuple(str(row[0]) for row in cur.fetchall())

        return self._use_cursor(_run)

    def set_agent_id(self, assistant_id: str, agent_id: str) -> None:
        def _run(cur: Any) -> None:
            cur.execute(
                """
                UPDATE lca_user_assistants
                SET agent_id = %s, status = 'active'
                WHERE assistant_id = %s
                """,
                (agent_id, assistant_id),
            )

        self._use_cursor(_run)

    def agent_id_of(self, assistant_id: str) -> str | None:
        def _run(cur: Any) -> str | None:
            cur.execute(
                "SELECT agent_id FROM lca_user_assistants WHERE assistant_id = %s",
                (assistant_id,),
            )
            row = cur.fetchone()
            if row is None or row[0] is None:
                return None
            return str(row[0])

        return self._use_cursor(_run)

    def set_onboarding_state(self, user_id: str, state: str) -> None:
        def _run(cur: Any) -> None:
            cur.execute(
                """
                UPDATE lca_users
                SET onboarding_state = %s, updated_at = now()
                WHERE user_id = %s
                """,
                (state, user_id),
            )

        self._use_cursor(_run)

    def get_onboarding_state(self, user_id: str) -> str:
        def _run(cur: Any) -> str:
            cur.execute(
                "SELECT onboarding_state FROM lca_users WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            return str(row[0]) if row is not None else "pending"

        return self._use_cursor(_run)


def build_user_assistant_store(
    *,
    database_url: str = "",
    sqlite_path: str | Path = _DEFAULT_PATH,
) -> AssistantOwnership:
    """按配置构造 store：Postgres URL 非空走 Postgres，否则 SQLite。"""
    if database_url.strip():
        return PostgresUserAssistantStore(database_url.strip())
    return SqliteUserAssistantStore(sqlite_path)


__all__ = [
    "PostgresUserAssistantStore",
    "SqliteUserAssistantStore",
    "build_user_assistant_store",
]
