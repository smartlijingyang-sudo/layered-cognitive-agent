"""Serialization and time validation for durable continuous work items."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime

from lca.contracts.harness.tasks.continuous import Trigger, TriggerKind, WorkItem


def work_item_payload(item: WorkItem) -> str:
    """Encode an immutable work definition as deterministic JSON."""

    data = asdict(item)
    trigger = data["trigger"]
    trigger["kind"] = item.trigger.kind.value
    trigger["occurred_at"] = timestamp(item.trigger.occurred_at)
    if item.available_at is not None:
        data["available_at"] = timestamp(item.available_at)
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def work_item_from_payload(payload: str) -> WorkItem:
    """Decode a durable work definition without trusting mutable queue columns."""

    raw = json.loads(payload)
    trigger_raw = raw["trigger"]
    trigger = Trigger(
        trigger_id=str(trigger_raw["trigger_id"]),
        kind=TriggerKind(trigger_raw["kind"]),
        occurred_at=parse_timestamp(str(trigger_raw["occurred_at"])),
        subject=str(trigger_raw["subject"]),
        payload=dict(trigger_raw.get("payload") or {}),
        idempotency_key=str(trigger_raw.get("idempotency_key") or ""),
    )
    available_at_raw = raw.get("available_at")
    return WorkItem(
        work_id=str(raw["work_id"]),
        trigger=trigger,
        profile=raw.get("profile"),
        preset=raw.get("preset"),
        session_id=raw.get("session_id"),
        message=str(raw.get("message") or ""),
        options=dict(raw.get("options") or {}),
        grant=tuple(str(item) for item in raw.get("grant") or ()),
        max_attempts=int(raw.get("max_attempts", 3)),
        available_at=(
            parse_timestamp(str(available_at_raw)) if available_at_raw is not None else None
        ),
    )


def max_attempts_from_payload(payload: str) -> int:
    """Expose retry ceiling to the SQLite claim query without duplicating fields."""

    return int(json.loads(payload).get("max_attempts", 3))


def timestamp(value: datetime) -> str:
    """Serialize a timezone-aware timestamp in ISO-8601 form."""

    return require_aware(value).isoformat()


def parse_timestamp(value: str) -> datetime:
    """Parse a persisted timestamp while preserving the control-plane time invariant."""

    return require_aware(datetime.fromisoformat(value))


def require_aware(value: datetime) -> datetime:
    """Reject naive time so lease expiry cannot vary with worker locale."""

    if value.tzinfo is None:
        raise ValueError("continuous control-plane times must be timezone-aware")
    return value


__all__ = [
    "max_attempts_from_payload",
    "parse_timestamp",
    "require_aware",
    "timestamp",
    "work_item_from_payload",
    "work_item_payload",
]
