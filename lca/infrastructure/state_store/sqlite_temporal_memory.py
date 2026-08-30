"""SQLite-backed temporal memory store.

Schema initialization and record encoding are delegated to focused modules.  This
adapter owns only the ``TemporalMemoryStore`` transaction semantics: persist,
revise, retire, relate, and query durable temporal facts.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path
from threading import RLock

from lca.contracts.models.core.memory import MemoryRecord, MemoryRelationKind
from lca.contracts.protocols.memory import TemporalMemoryStore
from lca.infrastructure.state_store.sqlite_temporal_codec import (
    TOKEN_PATTERN,
    materialize_record,
    normalize_scope,
    now_ms,
    record_values,
    row_to_record,
)
from lca.infrastructure.state_store.sqlite_temporal_schema import initialize_temporal_memory_schema

_MAX_RECALL_LIMIT = 50


class SqliteTemporalMemoryStore(TemporalMemoryStore):
    """Durable, scope-isolated temporal facts with lexical recall."""

    def __init__(self, path: str | Path = ".lca/temporal-memory.sqlite3") -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        initialize_temporal_memory_schema(self._conn)

    @property
    def path(self) -> Path:
        """Return the database path for diagnostics and tests."""
        return self._path

    def remember(self, record: MemoryRecord) -> MemoryRecord:
        """Append a fact once, normalizing temporal defaults at the persistence boundary."""
        materialized = materialize_record(record)
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO temporal_memory (
                    record_id, scope_id, content, memory_type, importance, recency_score,
                    source_trace_id, ttl, metadata_json, kind, provenance, confidence, deleted,
                    created_at_ms, observed_at_ms, valid_from_ms, valid_until_ms, retired_at_ms,
                    revision_of, trust
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                record_values(materialized),
            )
        return materialized

    def revise(
        self,
        record_id: str,
        replacement: MemoryRecord,
        *,
        reason: str = "revised",
    ) -> MemoryRecord:
        """Supersede a fact without destroying its historical validity interval."""
        current = now_ms()
        with self._lock, self._conn:
            previous = self._select_record(record_id)
            if previous is None:
                raise KeyError(f"temporal memory record {record_id!r} does not exist")
            if previous.retired_at_ms is not None:
                raise ValueError(f"temporal memory record {record_id!r} is already retired")
            replacement_scope = replacement.scope_id or previous.scope_id
            materialized = materialize_record(
                replace(
                    replacement,
                    scope_id=replacement_scope,
                    revision_of=record_id,
                    valid_from_ms=replacement.valid_from_ms or current,
                    metadata={
                        **previous.metadata,
                        **replacement.metadata,
                        "revision_reason": reason,
                    },
                ),
                at_ms=current,
            )
            if materialized.record_id == record_id:
                raise ValueError("replacement record_id must differ from the superseded record")
            self._conn.execute(
                "UPDATE temporal_memory SET valid_until_ms = ? WHERE record_id = ?",
                (materialized.valid_from_ms, record_id),
            )
            self._conn.execute(
                """
                INSERT INTO temporal_memory (
                    record_id, scope_id, content, memory_type, importance, recency_score,
                    source_trace_id, ttl, metadata_json, kind, provenance, confidence, deleted,
                    created_at_ms, observed_at_ms, valid_from_ms, valid_until_ms, retired_at_ms,
                    revision_of, trust
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                record_values(materialized),
            )
            self._conn.execute(
                """
                INSERT OR IGNORE INTO temporal_memory_relation(source_id, target_id, relation, created_at_ms)
                VALUES (?, ?, ?, ?)
                """,
                (record_id, materialized.record_id, MemoryRelationKind.SUPERSEDES.value, current),
            )
        return materialized

    def retire(self, record_id: str, *, reason: str = "retired", at_ms: int | None = None) -> None:
        """Soft-retire a fact while retaining it for audit and historical queries."""
        retired_at_ms = at_ms if at_ms is not None else now_ms()
        with self._lock, self._conn:
            cursor = self._conn.execute(
                """
                UPDATE temporal_memory
                SET deleted = 1,
                    retired_at_ms = COALESCE(retired_at_ms, ?),
                    valid_until_ms = COALESCE(valid_until_ms, ?),
                    metadata_json = json_set(metadata_json, '$.retirement_reason', ?)
                WHERE record_id = ?
                """,
                (retired_at_ms, retired_at_ms, reason, record_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"temporal memory record {record_id!r} does not exist")

    def relate(
        self,
        source_id: str,
        target_id: str,
        relation: MemoryRelationKind,
        *,
        created_at_ms: int | None = None,
    ) -> None:
        """Add an explicit non-destructive relation edge between two stored facts."""
        if source_id == target_id:
            raise ValueError("temporal memory relation endpoints must differ")
        created = created_at_ms if created_at_ms is not None else now_ms()
        with self._lock, self._conn:
            if self._select_record(source_id) is None or self._select_record(target_id) is None:
                raise KeyError("temporal memory relation requires two existing records")
            self._conn.execute(
                """
                INSERT OR IGNORE INTO temporal_memory_relation(source_id, target_id, relation, created_at_ms)
                VALUES (?, ?, ?, ?)
                """,
                (source_id, target_id, relation.value, created),
            )

    def recall(
        self,
        *,
        scope_id: str,
        query: str,
        as_of_ms: int | None = None,
        limit: int = 8,
    ) -> list[MemoryRecord]:
        """Recall active evidence using scope isolation, temporal validity, and lexical ranking."""
        effective_scope = normalize_scope(scope_id)
        as_of = as_of_ms if as_of_ms is not None else now_ms()
        capped_limit = max(1, min(limit, _MAX_RECALL_LIMIT))
        tokens = tuple(
            dict.fromkeys(token.casefold() for token in TOKEN_PATTERN.findall(query) if token)
        )
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM temporal_memory
                WHERE scope_id = ?
                  AND (deleted = 0 OR (retired_at_ms IS NOT NULL AND retired_at_ms > ?))
                  AND valid_from_ms <= ?
                  AND (valid_until_ms IS NULL OR valid_until_ms > ?)
                ORDER BY valid_from_ms DESC, importance DESC
                """,
                (effective_scope, as_of, as_of, as_of),
            ).fetchall()
        records = [row_to_record(row) for row in rows]
        if tokens:
            scored = [
                (
                    sum(record.content.casefold().count(token) for token in tokens),
                    record,
                )
                for record in records
                if any(token in record.content.casefold() for token in tokens)
            ]
            scored.sort(
                key=lambda item: (
                    item[0],
                    item[1].valid_from_ms or 0,
                    item[1].importance,
                ),
                reverse=True,
            )
            return [record for _, record in scored[:capped_limit]]
        return records[:capped_limit]

    def list_records(self, *, scope_id: str, include_retired: bool = False) -> list[MemoryRecord]:
        """List a scope's append-only records, optionally including soft-retired history."""
        effective_scope = normalize_scope(scope_id)
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM temporal_memory
                WHERE scope_id = ? AND (? = 1 OR deleted = 0)
                ORDER BY created_at_ms DESC
                """,
                (effective_scope, int(include_retired)),
            ).fetchall()
        return [row_to_record(row) for row in rows]

    def close(self) -> None:
        """Close the SQLite connection after all consumer work has finished."""
        with self._lock:
            self._conn.close()

    def _select_record(self, record_id: str) -> MemoryRecord | None:
        row = self._conn.execute(
            "SELECT * FROM temporal_memory WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        return row_to_record(row) if row is not None else None


__all__ = ["SqliteTemporalMemoryStore"]
