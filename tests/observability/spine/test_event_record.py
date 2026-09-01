"""Tests for EventRecord (Task 1.2)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from lca.infrastructure.observability.spine.event_record import EventRecord


def _rec(**overrides):
    base = {
        "execution_point": "brain.think.start",
        "channel": "fact",
        "span_id": "01HMABC",
        "parent_span_id": None,
        "sequence": 1,
        "epoch": 1,
        "causality_id": "sha256:abc",
        "outcome": None,
        "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        "when_corrected": datetime(2026, 9, 1, 12, 0, 0, 100000, tzinfo=timezone.utc),
        "prev_event_hash": None,
        "run_id": "r1",
        "step_id": "s1",
        "payload": {"k": 1},
    }
    base.update(overrides)
    return EventRecord(**base)


def test_event_record_immutable():
    rec = _rec()
    with pytest.raises(FrozenInstanceError):
        rec.sequence = 999  # type: ignore[misc]


def test_event_record_unknown_execution_point_rejected():
    with pytest.raises(ValueError, match="UnknownExecutionPoint"):
        _rec(execution_point="not.in.manifest")


def test_event_record_orphan_requires_reason():
    with pytest.raises(ValueError, match="orphan events MUST carry reason"):
        _rec(phase="orphan")


def test_event_record_orphan_with_reason_ok():
    rec = _rec(phase="orphan", reason="cancel_pre_boot")
    assert rec.phase == "orphan"
    assert rec.reason == "cancel_pre_boot"


def test_event_record_sequence_must_be_positive():
    with pytest.raises(ValueError, match="sequence must be > 0"):
        _rec(sequence=0)


def test_event_record_carries_minimum_schema():
    rec = _rec(outcome="success")
    assert rec.execution_point == "brain.think.start"
    assert rec.channel == "fact"
    assert rec.payload == {"k": 1}
