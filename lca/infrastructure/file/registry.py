"""FileIndexRegistry — SQLite-backed index for workspace files.

The filesystem tree is the single source of truth (SSOT).
This registry provides fast lookups and metadata queries for:
- Library views (user-visible deliverables)
- File readability classification for prompts
- Provenance tracking (source_chat_id)
- Recoverable trash state (trashed_at)
"""

from __future__ import annotations

import mimetypes
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.workspace.file_record import (
    FileRecord,
    ReadabilityTier,
    VisibilityTier,
    classify_readability,
    derive_visibility,
)


class FileIndexRegistry:
    """SQLite-backed index of all workspace files."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            from lca.infrastructure.path.locator import assistant_home
            db_path = assistant_home() / "workspace_files.db"
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self._db_path), timeout=5.0)
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA busy_timeout=5000;")
        con.row_factory = sqlite3.Row
        return con

    def _init_db(self) -> None:
        with self._get_connection() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS workspace_files (
                    file_id TEXT PRIMARY KEY,
                    path TEXT UNIQUE NOT NULL,
                    origin TEXT NOT NULL,
                    visibility TEXT NOT NULL,
                    goal_id TEXT,
                    mime TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    readability TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    source_chat_id TEXT,
                    trashed_at TEXT
                );
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_files_path ON workspace_files(path);")
            con.execute("CREATE INDEX IF NOT EXISTS idx_files_visibility ON workspace_files(visibility);")

    def register(self, record: FileRecord) -> None:
        with self._get_connection() as con:
            con.execute(
                """
                INSERT INTO workspace_files (
                    file_id, path, origin, visibility, goal_id, mime, size_bytes,
                    readability, created_at, updated_at, source_chat_id, trashed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    size_bytes=excluded.size_bytes,
                    mime=excluded.mime,
                    readability=excluded.readability,
                    updated_at=excluded.updated_at,
                    source_chat_id=COALESCE(excluded.source_chat_id, workspace_files.source_chat_id),
                    trashed_at=excluded.trashed_at;
                """,
                (
                    record.file_id,
                    record.path,
                    record.origin,
                    record.visibility.value,
                    record.goal_id,
                    record.mime,
                    record.size_bytes,
                    record.readability.value,
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                    record.source_chat_id,
                    record.trashed_at.isoformat() if record.trashed_at else None,
                ),
            )

    def get_by_path(self, path: str) -> FileRecord | None:
        clean = path.replace("\\", "/").lstrip("/")
        with self._get_connection() as con:
            cur = con.execute("SELECT * FROM workspace_files WHERE path = ? LIMIT 1;", (clean,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def get_by_id(self, file_id: str) -> FileRecord | None:
        with self._get_connection() as con:
            cur = con.execute("SELECT * FROM workspace_files WHERE file_id = ? LIMIT 1;", (file_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def list_files(
        self,
        visibility: VisibilityTier | None = None,
        include_trashed: bool = False,
    ) -> list[FileRecord]:
        query = "SELECT * FROM workspace_files WHERE 1=1"
        params: list[object] = []
        if not include_trashed:
            query += " AND trashed_at IS NULL"
        if visibility is not None:
            query += " AND visibility = ?"
            params.append(visibility.value)
        query += " ORDER BY updated_at DESC;"

        with self._get_connection() as con:
            cur = con.execute(query, params)
            return [self._row_to_record(r) for r in cur.fetchall()]

    def mark_trashed(self, path: str, trashed_at: datetime | None = None) -> bool:
        clean = path.replace("\\", "/").lstrip("/")
        ts = (trashed_at or datetime.now(timezone.utc)).isoformat()
        with self._get_connection() as con:
            cur = con.execute("UPDATE workspace_files SET trashed_at = ? WHERE path = ?;", (ts, clean))
            return cur.rowcount > 0

    def clear_trashed(self, path: str) -> bool:
        clean = path.replace("\\", "/").lstrip("/")
        with self._get_connection() as con:
            cur = con.execute("UPDATE workspace_files SET trashed_at = NULL WHERE path = ?;", (clean,))
            return cur.rowcount > 0

    def rebuild_index_from_fs(self, workspace_root: Path | str) -> int:
        """Scan workspace tree and rebuild the SQLite index matching filesystem reality."""
        root = Path(workspace_root)
        if not root.is_dir():
            return 0

        count = 0
        now = datetime.now(timezone.utc)
        for cur_root, dirs, files in os.walk(root):
            # Ignore hidden or internal dirs
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in files:
                if f.startswith("."):
                    continue
                full_path = Path(cur_root) / f
                try:
                    rel_path = str(full_path.relative_to(root)).replace("\\", "/")
                except ValueError:
                    continue

                stat = full_path.stat()
                mime, _ = mimetypes.guess_type(f)
                mime = mime or "application/octet-stream"
                vis = derive_visibility(rel_path)
                readability = classify_readability(f, mime)
                
                # Check if existing record exists to keep original file_id and created_at
                existing = self.get_by_path(rel_path)
                file_id = existing.file_id if existing else new_id("file")
                created_at = existing.created_at if existing else datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc)

                record = FileRecord(
                    file_id=file_id,
                    path=rel_path,
                    origin="upload" if rel_path.startswith("user/") else "agent_created",
                    visibility=vis,
                    mime=mime,
                    size_bytes=stat.st_size,
                    readability=readability,
                    created_at=created_at,
                    updated_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                )
                self.register(record)
                count += 1
        return count

    def _row_to_record(self, row: sqlite3.Row) -> FileRecord:
        trashed_at = datetime.fromisoformat(row["trashed_at"]) if row["trashed_at"] else None
        return FileRecord(
            file_id=row["file_id"],
            path=row["path"],
            origin=row["origin"],
            visibility=VisibilityTier(row["visibility"]),
            goal_id=row["goal_id"],
            mime=row["mime"],
            size_bytes=row["size_bytes"],
            readability=ReadabilityTier(row["readability"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            source_chat_id=row["source_chat_id"],
            trashed_at=trashed_at,
        )


__all__ = ["FileIndexRegistry"]
