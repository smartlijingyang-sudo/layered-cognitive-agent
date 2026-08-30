"""Normalize temporal memory records at the SQLite persistence boundary."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import replace
from time import time

from lca.contracts.atoms.enums import MemoryLayer, MemoryRecordKind
from lca.contracts.models.core.memory import MemoryRecord, MemoryTrust

DEFAULT_SCOPE = "local:default"
TOKEN_PATTERN = re.compile(r"[\w-]+", re.UNICODE)


def now_ms() -> int:
    """Return the current UNIX epoch in millisecond precision."""
    return int(time() * 1000)


def normalize_scope(scope_id: str) -> str:
    """Use the canonical local scope when a caller provides an empty value."""
    return scope_id.strip() or DEFAULT_SCOPE


def materialize_record(record: MemoryRecord, *, at_ms: int | None = None) -> MemoryRecord:
    """Fill temporal defaults before a record is persisted as an immutable fact."""
    current = at_ms if at_ms is not None else now_ms()
    created = record.created_at_ms if record.created_at_ms is not None else current
    observed = record.observed_at_ms if record.observed_at_ms is not None else created
    valid_from = record.valid_from_ms if record.valid_from_ms is not None else observed
    return replace(
        record,
        scope_id=normalize_scope(record.scope_id),
        created_at_ms=created,
        observed_at_ms=observed,
        valid_from_ms=valid_from,
    )


def record_values(record: MemoryRecord) -> tuple[object, ...]:
    """Encode a materialized record in the temporal_memory INSERT column order."""
    return (
        record.record_id,
        record.scope_id,
        record.content,
        record.memory_type.value,
        record.importance,
        record.recency_score,
        record.source_trace_id,
        record.ttl,
        json.dumps(record.metadata, ensure_ascii=False, default=str, sort_keys=True),
        record.kind.value,
        record.provenance,
        record.confidence,
        int(record.deleted),
        record.created_at_ms,
        record.observed_at_ms,
        record.valid_from_ms,
        record.valid_until_ms,
        record.retired_at_ms,
        record.revision_of,
        record.trust.value,
    )


def row_to_record(row: sqlite3.Row) -> MemoryRecord:
    """Decode one SQLite row into the complete typed temporal-memory record."""
    try:
        metadata = json.loads(str(row["metadata_json"]))
    except json.JSONDecodeError:
        metadata = {}
    return MemoryRecord(
        record_id=str(row["record_id"]),
        content=str(row["content"]),
        memory_type=MemoryLayer(str(row["memory_type"])),
        importance=float(row["importance"]),
        recency_score=float(row["recency_score"]) if row["recency_score"] is not None else None,
        source_trace_id=row["source_trace_id"],
        ttl=int(row["ttl"]) if row["ttl"] is not None else None,
        metadata=metadata if isinstance(metadata, dict) else {},
        kind=MemoryRecordKind(str(row["kind"])),
        provenance=str(row["provenance"]),
        confidence=float(row["confidence"]) if row["confidence"] is not None else None,
        deleted=bool(row["deleted"]),
        scope_id=str(row["scope_id"]),
        created_at_ms=int(row["created_at_ms"]),
        observed_at_ms=int(row["observed_at_ms"]),
        valid_from_ms=int(row["valid_from_ms"]),
        valid_until_ms=int(row["valid_until_ms"]) if row["valid_until_ms"] is not None else None,
        retired_at_ms=int(row["retired_at_ms"]) if row["retired_at_ms"] is not None else None,
        revision_of=row["revision_of"],
        trust=MemoryTrust(str(row["trust"])),
    )


__all__ = [
    "DEFAULT_SCOPE",
    "TOKEN_PATTERN",
    "materialize_record",
    "normalize_scope",
    "now_ms",
    "record_values",
    "row_to_record",
]
