"""Tests for BootTrace — frozen in-memory snapshot, never written to file."""

from __future__ import annotations

import pytest

from lca_kernel.stages import Stage
from lca_kernel.trace import BootTrace


def test_boot_trace_is_frozen_dataclass() -> None:
    """BootTrace must be immutable (frozen dataclass)."""
    from dataclasses import FrozenInstanceError

    trace = BootTrace(
        profile_path="/var/lca/profile.yaml",
        started_at=0.0,
        stages=(),
        outcome="booted",
        failure=None,
    )
    assert trace.profile_path == "/var/lca/profile.yaml"
    assert trace.started_at == 0.0
    assert trace.outcome == "booted"
    assert trace.failure is None
    # Frozen: mutation must raise.
    with pytest.raises(FrozenInstanceError):
        trace.outcome = "failed"  # type: ignore[misc]


def test_boot_trace_carries_stages_in_chronological_order() -> None:
    """``stages`` is a tuple of (Stage, ts, status) triples."""
    trace = BootTrace(
        profile_path="x",
        started_at=0.0,
        stages=(
            (Stage.SOURCE, 0.001, "ok"),
            (Stage.RESOLVE, 0.002, "ok"),
            (Stage.BOOT, 0.003, "failed"),
        ),
        outcome="failed",
        failure=RuntimeError("boom"),
    )
    assert len(trace.stages) == 3
    assert trace.stages[0][0] is Stage.SOURCE
    assert trace.stages[-1][2] == "failed"
    assert isinstance(trace.failure, RuntimeError)


def test_boot_trace_outcome_literal_typing() -> None:
    """``outcome`` accepts only booted / failed / disposed."""
    for literal in ("booted", "failed", "disposed"):
        trace = BootTrace(
            profile_path="p",
            started_at=0.0,
            stages=(),
            outcome=literal,  # type: ignore[arg-type]
            failure=None,
        )
        assert trace.outcome == literal
