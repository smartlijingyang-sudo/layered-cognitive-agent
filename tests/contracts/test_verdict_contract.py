"""Contract tests for the typed think verdict dataclass.

Per ADR-0206 §5.6 + the 2026-09-09 think subgraph decompress plan: the
think subgraph emits a typed ``verdict.v1`` fact at its terminal sink
(``phase.think.verdict_emit``) so projection / replay / audit have one
SSOT instead of stitching ``decision`` + ``gate_chain`` strings.

These tests pin the contract surface; the runtime emitter arrives in
Task 4 of the same PR.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass
from datetime import UTC, datetime

import pytest

from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.execution.verdict import VERDICT_SCHEMA_VERSION, Verdict


def _dec() -> Decision:
    return Decision(
        decision_id="dec_001",
        action_type="respond",
        rationale="unit test",
        confidence=1.0,
    )


def test_verdict_is_frozen_dataclass() -> None:
    """Verdict must be a frozen dataclass — terminal projection, never mutated."""
    assert is_dataclass(Verdict)
    v = Verdict(
        decision_id="dec_001",
        action_type="respond",
        gate_chain=("DecisionGateChained",),
        ts=datetime(2026, 9, 9, tzinfo=UTC),
        source_phase="think",
    )
    with pytest.raises(FrozenInstanceError):
        v.decision_id = "dec_002"  # type: ignore[misc]


def test_verdict_field_set_is_stable() -> None:
    """Adding a field is a contract change; lock the field set today."""
    names = {f.name for f in fields(Verdict)}
    assert names == {
        "decision_id",
        "action_type",
        "gate_chain",
        "ts",
        "source_phase",
        "schema_version",
    }


def test_verdict_schema_version_is_locked() -> None:
    """Schema version is the public discriminator; bump = ADR bump."""
    v = Verdict(
        decision_id="d",
        action_type="respond",
        gate_chain=("g",),
        ts=datetime(2026, 9, 9, tzinfo=UTC),
        source_phase="think",
    )
    assert v.schema_version == VERDICT_SCHEMA_VERSION == "v1"


def test_verdict_gate_chain_is_tuple_of_strings() -> None:
    """Gate chain must be a tuple (frozen, hashable) of non-empty strings."""
    v = Verdict(
        decision_id="d",
        action_type="respond",
        gate_chain=("DecisionGateChained", "BudgetGuard"),
        ts=datetime(2026, 9, 9, tzinfo=UTC),
        source_phase="think",
    )
    assert v.gate_chain == ("DecisionGateChained", "BudgetGuard")
    assert isinstance(v.gate_chain, tuple)
    assert all(isinstance(label, str) and label for label in v.gate_chain)


def test_verdict_from_decision_carries_id_and_action() -> None:
    """Constructor helper mirrors Decision's decision_id + action_type."""
    v = Verdict.from_decision(
        decision=_dec(),
        gate_chain=("DecisionGateChained",),
        ts=datetime(2026, 9, 9, tzinfo=UTC),
    )
    assert v.decision_id == "dec_001"
    assert v.action_type == "respond"
    assert v.gate_chain == ("DecisionGateChained",)
    assert v.source_phase == "think"


def test_verdict_from_decision_rejects_empty_gate_chain() -> None:
    """Empty gate_chain is meaningless (would mean 'no gate fired' = bug)."""
    with pytest.raises(ValueError, match="gate_chain"):
        Verdict.from_decision(
            decision=_dec(),
            gate_chain=(),
            ts=datetime(2026, 9, 9, tzinfo=UTC),
        )


def test_verdict_rejects_empty_decision_id() -> None:
    """decision_id is the SSOT join key; empty = contract violation."""
    with pytest.raises(ValueError, match="decision_id"):
        Verdict(
            decision_id="",
            action_type="respond",
            gate_chain=("g",),
            ts=datetime(2026, 9, 9, tzinfo=UTC),
            source_phase="think",
        )


def test_verdict_rejects_empty_action_type() -> None:
    """action_type is the projection discriminator; empty = contract violation."""
    with pytest.raises(ValueError, match="action_type"):
        Verdict(
            decision_id="d",
            action_type="",
            gate_chain=("g",),
            ts=datetime(2026, 9, 9, tzinfo=UTC),
            source_phase="think",
        )


def test_verdict_rejects_unknown_source_phase() -> None:
    """source_phase is closed for now (think is the only emitter)."""
    with pytest.raises(ValueError, match="source_phase"):
        Verdict(
            decision_id="d",
            action_type="respond",
            gate_chain=("g",),
            ts=datetime(2026, 9, 9, tzinfo=UTC),
            source_phase="perceive",
        )


def test_verdict_rejects_naive_timestamp() -> None:
    """ts must be timezone-aware; naive datetime breaks replay determinism."""
    with pytest.raises(ValueError, match="timezone-aware"):
        Verdict(
            decision_id="d",
            action_type="respond",
            gate_chain=("g",),
            ts=datetime(2026, 9, 9),  # no tzinfo
            source_phase="think",
        )


def test_verdict_is_hashable() -> None:
    """Frozen + tuple field → verdict is hashable; usable as projection key."""
    v = Verdict(
        decision_id="d",
        action_type="respond",
        gate_chain=("g",),
        ts=datetime(2026, 9, 9, tzinfo=UTC),
        source_phase="think",
    )
    assert hash(v) == hash(v)
    assert {v, v} == {v}


def test_verdict_equality_is_field_based() -> None:
    """Frozen dataclass equality is field-based — projection fold relies on this."""
    kwargs = {
        "decision_id": "d",
        "action_type": "respond",
        "gate_chain": ("g",),
        "ts": datetime(2026, 9, 9, tzinfo=UTC),
        "source_phase": "think",
    }
    assert Verdict(**kwargs) == Verdict(**kwargs)
