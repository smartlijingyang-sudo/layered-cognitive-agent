"""Conversation 持久化 —— SQLite 最小形态（BE-4）。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lca.contracts.atoms.ids import new_id

_DEFAULT_DB = Path("traces/conversations.db")


@dataclass(frozen=True)
class TurnRecord:
    turn_id: str
    run_id: str
    trace_id: str
    question: str
    mode: str
    track: str
    status: str
    created_at: float


@dataclass(frozen=True)
class ConversationRecord:
    conversation_id: str
    title: str
    created_at: float
    turns: tuple[TurnRecord, ...]


class ConversationStore:
    """SQLite 会话存储（单租户 MVP）。"""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path if db_path is not None else _DEFAULT_DB
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS turns (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    track TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                );
                CREATE INDEX IF NOT EXISTS idx_turns_conversation
                    ON turns(conversation_id, created_at);
                """
            )

    def create_conversation(self, *, title: str) -> dict[str, Any]:
        import time

        conversation_id = new_id("conv")
        created_at = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, created_at) VALUES (?, ?, ?)",
                (conversation_id, title.strip() or "新对话", created_at),
            )
        return {
            "conversation_id": conversation_id,
            "title": title.strip() or "新对话",
            "created_at": created_at,
            "turns": [],
        }

    def list_conversations(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, title, created_at FROM conversations ORDER BY created_at DESC"
            ).fetchall()
        return [
            {"conversation_id": row["id"], "title": row["title"], "created_at": row["created_at"]}
            for row in rows
        ]

    def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, title, created_at FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if row is None:
                return None
            turns = conn.execute(
                """
                SELECT id, run_id, trace_id, question, mode, track, status, created_at
                FROM turns WHERE conversation_id = ? ORDER BY created_at ASC
                """,
                (conversation_id,),
            ).fetchall()
        return {
            "conversation_id": row["id"],
            "title": row["title"],
            "created_at": row["created_at"],
            "turns": [self._turn_row(t) for t in turns],
        }

    def add_turn(
        self,
        conversation_id: str,
        *,
        run_id: str,
        trace_id: str,
        question: str,
        mode: str,
        track: str,
        status: str = "pending",
    ) -> dict[str, Any] | None:
        import time

        if self.get_conversation(conversation_id) is None:
            return None
        turn_id = new_id("turn")
        created_at = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO turns
                (id, conversation_id, run_id, trace_id, question, mode, track, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    turn_id,
                    conversation_id,
                    run_id,
                    trace_id,
                    question,
                    mode,
                    track,
                    status,
                    created_at,
                ),
            )
        return self._turn_row(
            {
                "id": turn_id,
                "run_id": run_id,
                "trace_id": trace_id,
                "question": question,
                "mode": mode,
                "track": track,
                "status": status,
                "created_at": created_at,
            }
        )

    def update_turn_status(self, run_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE turns SET status = ? WHERE run_id = ?", (status, run_id))

    @staticmethod
    def _turn_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        if isinstance(row, sqlite3.Row):
            data = dict(row)
            return {
                "turn_id": data["id"],
                "run_id": data["run_id"],
                "trace_id": data["trace_id"],
                "question": data["question"],
                "mode": data["mode"],
                "track": data["track"],
                "status": data["status"],
                "created_at": data["created_at"],
            }
        return {
            "turn_id": row["id"],
            "run_id": row["run_id"],
            "trace_id": row["trace_id"],
            "question": row["question"],
            "mode": row["mode"],
            "track": row["track"],
            "status": row["status"],
            "created_at": row["created_at"],
        }

    def dump_json(self, conversation_id: str) -> str:
        payload = self.get_conversation(conversation_id)
        if payload is None:
            return "{}"
        return json.dumps(payload, ensure_ascii=False)
