"""Resume point ``paused_at`` round-trip and snapshot ``created_at`` mapping.

Regression coverage for the HITL wall-clock budget fix: the pause time must
survive the serialization round-trip so the resumed run can exclude the
paused duration from its wall-clock budget.
"""

from __future__ import annotations

import time

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


def test_ra159_snapshot_paused_at_field_replaces_created_at_overload() -> None:
    """RA-159: pause 时间走显式 paused_at 字段；created_at 恢复"快照创建时间"单语义。

    旧测试钉的是被 RA-159 要求废除的重载契约（created_at 双语义），随契约变更而更新，
    不是"修掉测试"——wall-clock 回归覆盖仍在（paused_at round-trip + 下面的秒数测试）。
    """
    point = _point(paused_at=_PAUSED_AT)
    snapshot = resume_point_to_state_snapshot(point)
    assert snapshot.paused_at is not None
    assert snapshot.paused_at.timestamp() == pytest.approx(_PAUSED_AT)
    # created_at 不再是暂停时刻（2009 年），而是快照创建时间（约现在）
    assert abs(time.time() - snapshot.created_at.timestamp()) < 120


def test_ra159_snapshot_without_paused_at_round_trips_to_zero() -> None:
    """RA-159: 老 bundle（无 paused_at）-> snapshot.paused_at 为 None -> 反向提取得 0.0。"""
    snapshot = resume_point_to_state_snapshot(_point(paused_at=0.0))
    assert snapshot.paused_at is None
    point = resume_point_from_state_snapshot("ap-1", snapshot)
    assert point.paused_at == 0.0


def test_ra159_paused_seconds_since_reads_explicit_field() -> None:
    """RA-159: _paused_seconds_since 读显式字段；None -> 0（老快照兼容，补 Q5 测试缺口）。"""
    from lca.runtime.loop.runtime_loop import _paused_seconds_since

    with_paused = resume_point_to_state_snapshot(_point(paused_at=time.time() - 60))
    assert _paused_seconds_since(with_paused) == pytest.approx(60, abs=5)
    legacy = resume_point_to_state_snapshot(_point(paused_at=0.0))
    assert _paused_seconds_since(legacy) == 0.0


def test_resume_point_from_snapshot_extracts_paused_at() -> None:
    snapshot = resume_point_to_state_snapshot(_point(paused_at=_PAUSED_AT))
    point = resume_point_from_state_snapshot("ap-1", snapshot)
    assert point.paused_at == pytest.approx(_PAUSED_AT)


def test_resume_point_round_trip_defaults_paused_at_zero() -> None:
    point = _point()
    restored = deserialize_resume_point(serialize_resume_point(point))
    assert restored.paused_at == 0.0
