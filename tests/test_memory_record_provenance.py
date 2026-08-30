from __future__ import annotations

import pytest

from lca.contracts.atoms.enums import MemoryLayer
from lca.contracts.models.core.memory import MemoryRecord


def test_memory_record_accepts_provenance_and_confidence() -> None:
    record = MemoryRecord(
        "r1",
        "fact",
        MemoryLayer.SEMANTIC,
        0.8,
        provenance="crm",
        confidence=0.9,
    )
    assert record.provenance == "crm"
    assert record.confidence == 0.9


def test_memory_record_rejects_invalid_confidence() -> None:
    with pytest.raises(ValueError):
        MemoryRecord("r1", "fact", MemoryLayer.SEMANTIC, 0.8, confidence=1.1)


def test_memory_record_supports_tombstone_deletion() -> None:
    record = MemoryRecord(
        "r1",
        "revoked fact",
        MemoryLayer.SEMANTIC,
        0.5,
        deleted=True,
    )

    assert record.deleted is True
