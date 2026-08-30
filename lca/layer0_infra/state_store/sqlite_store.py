"""Durable SQLite implementation of the ``StateStore`` protocol.

The StateStore contract carries complete ``AgentState`` objects whose working
memory and history intentionally allow typed, extensible values.  This backend
therefore stores a trusted, local pickle payload rather than silently degrading
those values into lossy JSON.  The database is an internal runtime artifact;
it must not be writable by untrusted principals or opened from an untrusted
path.  A SHA-256 digest detects accidental corruption before deserialization.
"""

from __future__ import annotations

import asyncio
import pickle
import sqlite3
from hashlib import sha256
from pathlib import Path
from time import time

from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import StateStore


class SqliteStateStore(StateStore):
    """Persist complete trusted ``AgentState`` snapshots in one SQLite database.

    Each trace/step pair has one canonical checkpoint.  Re-saving the same pair
    atomically replaces the payload, which matches the StateStore's latest-state
    semantics while keeping state references deterministic for resume paths.
    """

    def __init__(self, database_path: Path | str) -> None:
        self._database_path = Path(database_path)
        if str(self._database_path) == ":memory:":
            raise ValueError("SqliteStateStore requires an on-disk database path")

    async def save(self, state: AgentState) -> str:
        """Durably save ``state`` and return its stable SQLite state reference."""

        trace_id = state.trace_id.strip()
        if not trace_id:
            raise ValueError("AgentState.trace_id must not be empty")
        state_ref = f"sqlite://{trace_id}/{state.step}"
        payload = pickle.dumps(state, protocol=pickle.HIGHEST_PROTOCOL)
        digest = sha256(payload).hexdigest()
        await asyncio.to_thread(self._save_payload, state_ref, payload, digest)
        return state_ref

    async def load(self, state_ref: str) -> AgentState:
        """Load one previously saved state, rejecting unknown or corrupt records."""

        return await asyncio.to_thread(self._load_state, state_ref)

    def _save_payload(self, state_ref: str, payload: bytes, digest: str) -> None:
        with self._connect() as connection:
            self._ensure_schema(connection)
            connection.execute(
                """
                INSERT INTO agent_state_snapshots(state_ref, payload, sha256, updated_at_ms)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(state_ref) DO UPDATE SET
                    payload = excluded.payload,
                    sha256 = excluded.sha256,
                    updated_at_ms = excluded.updated_at_ms
                """,
                (state_ref, sqlite3.Binary(payload), digest, int(time() * 1000)),
            )

    def _load_state(self, state_ref: str) -> AgentState:
        with self._connect() as connection:
            self._ensure_schema(connection)
            row = connection.execute(
                "SELECT payload, sha256 FROM agent_state_snapshots WHERE state_ref = ?",
                (state_ref,),
            ).fetchone()
        if row is None:
            raise KeyError(state_ref)
        payload = bytes(row["payload"])
        expected_digest = str(row["sha256"])
        if sha256(payload).hexdigest() != expected_digest:
            raise ValueError(f"state snapshot digest mismatch: {state_ref}")
        # The database is a private runtime artifact written by this service only.
        state = pickle.loads(payload)  # noqa: S301
        if not isinstance(state, AgentState):
            raise TypeError(f"state snapshot has unexpected type: {type(state).__name__}")
        return state

    def _connect(self) -> sqlite3.Connection:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_state_snapshots (
                state_ref TEXT PRIMARY KEY,
                payload BLOB NOT NULL,
                sha256 TEXT NOT NULL,
                updated_at_ms INTEGER NOT NULL
            )
            """
        )


__all__ = ["SqliteStateStore"]
