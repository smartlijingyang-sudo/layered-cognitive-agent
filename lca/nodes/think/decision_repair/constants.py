"""Shared outcome sentinels for think decision repair."""

from __future__ import annotations

_REASON_OK: str = "decision_ok"
_REASON_REPAIRED: str = "decision_repaired"
_REASON_REJECTED_SCHEMA: str = "decision_rejected_schema"
_REASON_REJECTED_TRUNCATED: str = "decision_rejected_truncated"

# Outcome sentinels for the per-call validation loop. Strings rather
# than an enum so the function stays allocation-free at runtime; the
# caller branches on identity (these are module-level singletons).
_OK: str = "ok"
_REPAIR_SUCCEEDED: str = "repair_succeeded"
_REPAIR_REJECTED: str = "repair_rejected"
_SCHEMA_REJECTED: str = "schema_rejected"


__all__ = [
    "_OK",
    "_REASON_OK",
    "_REASON_REJECTED_SCHEMA",
    "_REASON_REJECTED_TRUNCATED",
    "_REASON_REPAIRED",
    "_REPAIR_REJECTED",
    "_REPAIR_SUCCEEDED",
    "_SCHEMA_REJECTED",
]
