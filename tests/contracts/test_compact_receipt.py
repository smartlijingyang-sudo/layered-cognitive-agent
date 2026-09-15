"""Contract tests for the ``CompactReceipt`` DTO.

PR-3.8.2: pins the typed-boundary DTO emitted by
``think.context.compact``. ADR-0195 §1.4 / C13 requires every cross-
boundary transfer to be a frozen Pydantic model with ``extra="forbid"``;
these tests hold that contract.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from lca.contracts.dto.compact_receipt import CompactReceipt, CompactStrategy


def _sample_at() -> datetime:
    return datetime(2026, 9, 15, 12, 0, 0, tzinfo=UTC)


def test_compact_receipt_is_frozen() -> None:
    """``CompactReceipt`` is frozen: no field can be reassigned."""
    receipt = CompactReceipt(
        compacted=True,
        bytes_before=100,
        bytes_after=50,
        strategy="truncate_oldest",
        at=_sample_at(),
    )
    with pytest.raises((dataclasses.FrozenInstanceError, ValidationError, AttributeError)):
        receipt.bytes_before = 200  # type: ignore[misc]


def test_compact_receipt_rejects_extra_fields() -> None:
    """``extra="forbid"`` rejects unknown fields (C13 cross-boundary contract)."""
    with pytest.raises(ValidationError) as exc_info:
        CompactReceipt(
            compacted=True,
            bytes_before=100,
            bytes_after=50,
            strategy="truncate_oldest",
            at=_sample_at(),
            rogue_field="noise",
        )
    assert "rogue_field" in str(exc_info.value)


@pytest.mark.parametrize(
    "strategy",
    ["noop", "truncate_oldest", "summarize", "spill"],
)
def test_compact_receipt_accepts_valid_strategies(strategy: CompactStrategy) -> None:
    """All four ``CompactStrategy`` literals round-trip."""
    receipt = CompactReceipt(
        compacted=strategy != "noop",
        bytes_before=100,
        bytes_after=100 if strategy == "noop" else 50,
        strategy=strategy,
        at=_sample_at(),
    )
    assert receipt.strategy == strategy


def test_compact_receipt_rejects_unknown_strategy() -> None:
    """Literal enforcement: unknown strategy is rejected at construction."""
    with pytest.raises(ValidationError):
        CompactReceipt(
            compacted=True,
            bytes_before=100,
            bytes_after=50,
            strategy="bogus",  # type: ignore[arg-type]
            at=_sample_at(),
        )


def test_compact_receipt_at_field_is_timezone_aware() -> None:
    """``at`` preserves tzinfo — UTC construction is a typed seam, not a string."""
    receipt = CompactReceipt(
        compacted=True,
        bytes_before=10,
        bytes_after=5,
        strategy="truncate_oldest",
        at=_sample_at(),
    )
    assert receipt.at.tzinfo is not None
    assert receipt.at.utcoffset() == timedelta(0)


def test_compact_receipt_noop_factory() -> None:
    """``CompactReceipt.noop`` returns ``strategy="noop"`` and equal byte counts."""
    receipt = CompactReceipt.noop(bytes_seen=42)
    assert receipt.compacted is False
    assert receipt.bytes_before == 42
    assert receipt.bytes_after == 42
    assert receipt.strategy == "noop"
    assert receipt.at.tzinfo is not None


def test_compact_receipt_applied_factory_records_compaction() -> None:
    """``CompactReceipt.applied`` enforces ``bytes_after <= bytes_before``."""
    receipt = CompactReceipt.applied(
        bytes_before=200,
        bytes_after=80,
        strategy="truncate_oldest",
    )
    assert receipt.compacted is True
    assert receipt.bytes_before == 200
    assert receipt.bytes_after == 80
    assert receipt.strategy == "truncate_oldest"


def test_compact_receipt_applied_rejects_noop_strategy() -> None:
    """``applied`` must take a non-noop strategy; noop has its own factory."""
    with pytest.raises(ValueError, match="non-noop"):
        CompactReceipt.applied(
            bytes_before=100,
            bytes_after=100,
            strategy="noop",
        )


def test_compact_receipt_applied_rejects_payload_growth() -> None:
    """``applied`` must not grow the payload (a typo guard, not a runtime seam)."""
    with pytest.raises(ValueError, match="must not grow"):
        CompactReceipt.applied(
            bytes_before=50,
            bytes_after=100,
            strategy="truncate_oldest",
        )


def test_compact_receipt_skipped_factory() -> None:
    """``skipped`` records an empty/noop receipt on the error path."""
    receipt = CompactReceipt.skipped(bytes_seen=77)
    assert receipt.compacted is False
    assert receipt.bytes_before == 77
    assert receipt.bytes_after == 77
    assert receipt.strategy == "noop"
    assert receipt.at.tzinfo is not None


def test_compact_receipt_at_round_trips_through_serialization() -> None:
    """``model_dump`` preserves ``at`` as a tz-aware datetime."""
    receipt = CompactReceipt(
        compacted=False,
        bytes_before=5,
        bytes_after=5,
        strategy="noop",
        at=_sample_at(),
    )
    dumped = receipt.model_dump()
    assert isinstance(dumped["at"], datetime)
    assert dumped["at"].tzinfo is not None
    assert dumped["at"] == _sample_at()


def test_compact_receipt_equality_is_field_based() -> None:
    """Pydantic frozen models compare by field value, not identity."""
    a = CompactReceipt(
        compacted=False,
        bytes_before=10,
        bytes_after=10,
        strategy="noop",
        at=_sample_at(),
    )
    b = CompactReceipt(
        compacted=False,
        bytes_before=10,
        bytes_after=10,
        strategy="noop",
        at=_sample_at(),
    )
    assert a == b
