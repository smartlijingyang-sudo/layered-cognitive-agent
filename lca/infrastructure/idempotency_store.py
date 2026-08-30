"""Filesystem-backed effect idempotency storage.

The store deliberately persists only the claim state and the receipt. It does
not retry an ``in_progress`` claim: an interrupted external effect is
uncertain and must be handled by the recovery policy instead of being issued a
second time.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Final

from lca.contracts.models.core.decision import Observation
from lca.contracts.protocols.idempotency import IdempotencyClaim, IdempotencyStore

_DEFAULT_PATH: Final[Path] = Path("traces/runtime/idempotency.sqlite3")
_OBSERVATION_TAG: Final[str] = f"{Observation.__module__}:{Observation.__qualname__}"


class IdempotencyStoreCorruptError(RuntimeError):
    """Raised when a completed receipt cannot be decoded safely."""


class SqliteIdempotencyStore(IdempotencyStore):
    """Durable ``IdempotencyStore`` backed by SQLite.

    SQLite transactions provide the atomic claim boundary across event loops,
    threads, and processes. WAL mode permits readers while a claim is being
    committed, and ``synchronous=FULL`` makes a completed receipt durable
    before ``complete`` returns.
    """

    def __init__(self, path: str | Path = _DEFAULT_PATH) -> None:
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=30.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        if str(self.path) != ":memory:":
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS effect_idempotency (
                    plan_ref TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('in_progress', 'completed')),
                    receipt_json TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (plan_ref, idempotency_key)
                )
                """
            )

    async def claim(self, plan_ref: str, idempotency_key: str) -> IdempotencyClaim:
        """Atomically create or read a claim."""
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT status, receipt_json
                FROM effect_idempotency
                WHERE plan_ref = ? AND idempotency_key = ?
                """,
                (plan_ref, idempotency_key),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO effect_idempotency
                        (plan_ref, idempotency_key, status, receipt_json, updated_at)
                    VALUES (?, ?, 'in_progress', NULL, ?)
                    """,
                    (plan_ref, idempotency_key, _timestamp()),
                )
                return IdempotencyClaim(status="new")
            if row["status"] == "in_progress":
                return IdempotencyClaim(status="in_progress")
            if row["status"] == "completed":
                try:
                    receipt = _decode_receipt(json.loads(row["receipt_json"]))
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise IdempotencyStoreCorruptError(
                        f"cannot decode receipt for {plan_ref!r}/{idempotency_key!r}"
                    ) from exc
                return IdempotencyClaim(status="completed", receipt=receipt)
            raise IdempotencyStoreCorruptError(
                f"unknown idempotency status {row['status']!r} for {plan_ref!r}/{idempotency_key!r}"
            )

    async def complete(self, plan_ref: str, idempotency_key: str, receipt: object) -> None:
        """Durably commit a receipt for an existing in-progress claim."""
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT status
                FROM effect_idempotency
                WHERE plan_ref = ? AND idempotency_key = ?
                """,
                (plan_ref, idempotency_key),
            ).fetchone()
            if row is None:
                raise KeyError(f"idempotency claim does not exist: {plan_ref}/{idempotency_key}")
            if row["status"] == "completed":
                return
            if row["status"] != "in_progress":
                raise IdempotencyStoreCorruptError(
                    f"cannot complete claim with status {row['status']!r}"
                )
            encoded = _encode_receipt(receipt)
            receipt_json = json.dumps(encoded, ensure_ascii=False, separators=(",", ":"))
            connection.execute(
                """
                UPDATE effect_idempotency
                SET status = 'completed', receipt_json = ?, updated_at = ?
                WHERE plan_ref = ? AND idempotency_key = ?
                """,
                (receipt_json, _timestamp(), plan_ref, idempotency_key),
            )


def _timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def _encode_receipt(value: object) -> object:
    """Encode receipt values using a closed, JSON-safe representation."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return {"__lca_type__": "enum", "value": value.value}
    if isinstance(value, datetime):
        return {"__lca_type__": "datetime", "value": value.isoformat()}
    if isinstance(value, Mapping):
        return {str(key): _encode_receipt(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode_receipt(item) for item in value]
    if is_dataclass(value) and isinstance(value, Observation):
        return {
            "__lca_type__": "dataclass",
            "name": _OBSERVATION_TAG,
            "fields": {
                field.name: _encode_receipt(getattr(value, field.name)) for field in fields(value)
            },
        }
    raise TypeError(f"receipt value is not durably serializable: {type(value).__name__}")


def _decode_receipt(value: object) -> object:
    if isinstance(value, list):
        return [_decode_receipt(item) for item in value]
    if not isinstance(value, dict):
        return value
    kind = value.get("__lca_type__")
    if kind == "enum":
        return value.get("value")
    if kind == "datetime":
        return datetime.fromisoformat(str(value["value"]))
    if kind == "dataclass" and value.get("name") == _OBSERVATION_TAG:
        raw_fields = value.get("fields")
        if not isinstance(raw_fields, dict):
            raise TypeError("Observation receipt fields must be an object")
        decoded = {key: _decode_receipt(item) for key, item in raw_fields.items()}
        return Observation(**decoded)
    if "__lca_type__" in value:
        raise TypeError(f"unsupported receipt type tag: {kind!r}")
    return {str(key): _decode_receipt(item) for key, item in value.items()}


__all__ = ["IdempotencyStoreCorruptError", "SqliteIdempotencyStore"]
