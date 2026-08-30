"""SQLite schema initialization for durable temporal-memory facts and relations."""

from __future__ import annotations

import sqlite3

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS temporal_memory (
    record_id TEXT PRIMARY KEY,
    scope_id TEXT NOT NULL,
    content TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    importance REAL NOT NULL,
    recency_score REAL,
    source_trace_id TEXT,
    ttl INTEGER,
    metadata_json TEXT NOT NULL,
    kind TEXT NOT NULL,
    provenance TEXT NOT NULL,
    confidence REAL,
    deleted INTEGER NOT NULL DEFAULT 0,
    created_at_ms INTEGER NOT NULL,
    observed_at_ms INTEGER NOT NULL,
    valid_from_ms INTEGER NOT NULL,
    valid_until_ms INTEGER,
    retired_at_ms INTEGER,
    revision_of TEXT,
    trust TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_temporal_memory_scope_valid
    ON temporal_memory(scope_id, deleted, valid_from_ms, valid_until_ms);
CREATE INDEX IF NOT EXISTS idx_temporal_memory_scope_created
    ON temporal_memory(scope_id, created_at_ms DESC);
CREATE TABLE IF NOT EXISTS temporal_memory_relation (
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL,
    PRIMARY KEY(source_id, target_id, relation),
    FOREIGN KEY(source_id) REFERENCES temporal_memory(record_id),
    FOREIGN KEY(target_id) REFERENCES temporal_memory(record_id)
);
CREATE INDEX IF NOT EXISTS idx_temporal_memory_relation_source
    ON temporal_memory_relation(source_id);
"""


def initialize_temporal_memory_schema(connection: sqlite3.Connection) -> None:
    """Create the temporal-memory row and relation schema if it does not exist."""
    with connection:
        connection.executescript(_SCHEMA_SQL)


__all__ = ["initialize_temporal_memory_schema"]
