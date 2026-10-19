"""Resume point ``paused_at`` round-trip and snapshot ``created_at`` mapping.

Regression coverage for the HITL wall-clock budget fix: the pause time must
survive the serialization round-trip so the resumed run can exclude the
paused duration from its wall-clock budget.
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.ids.ids import RunId, TraceId
from lca.contracts.harness.collaboration.agent import ApprovalResumePoint
from lca.plugins.session.runtime.resume.point import (
    deserialize_resume_point,
    resume_point_from_state_snapshot,
    resume_point_to_state_snapshot,
    serialize_resume_point,
)

_PAUSED_AT = 1_234_567_890.0


def _point(paused_at: float = 0.0) -> ApprovalResumePoint:
    return ApprovalResumePoint(
        approval_id="ap-1",
        snapshot_id="snap-1",
        step=1,
        state_ref="state-1",
        plan_ref="plan-1",
        node_id="perceive.main",
        visit_counts=(("perceive.main", 1),),
        edge_counts=(("a", "b", 1),),
        artifacts={},
        causation_refs=(),
        budget_snapshot={},
        trace_id=TraceId("trace-1"),
        run_id=RunId("run_1"),
        paused_at=paused_at,
    )


def test_resume_point_round_trip_preserves_paused_at() -> None:
    point = _point(paused_at=_PAUSED_AT)
    restored = deserialize_resume_point(serialize_resume_point(point))
    assert restored.paused_at == pytest.approx(_PAUSED_AT)


def test_resume_point_to_snapshot_maps_paused_at_to_created_at() -> None:
    point = _point(paused_at=_PAUSED_AT)
    snapshot = resume_point_to_state_snapshot(point)
    assert snapshot.created_at is not None
    assert snapshot.created_at.timestamp() == pytest.approx(_PAUSED_AT)


def test_resume_point_from_snapshot_extracts_paused_at() -> None:
    snapshot = resume_point_to_state_snapshot(_point(paused_at=_PAUSED_AT))
    point = resume_point_from_state_snapshot("ap-1", snapshot)
    assert point.paused_at == pytest.approx(_PAUSED_AT)


def test_resume_point_round_trip_defaults_paused_at_zero() -> None:
    point = _point()
    restored = deserialize_resume_point(serialize_resume_point(point))
    assert restored.paused_at == 0.0
