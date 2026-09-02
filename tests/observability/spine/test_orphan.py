"""Tests for PR-6 orphan-event semantics (ADR-0165.1 §19, design §4.3).

orphan events 携带 ``phase="orphan"`` + ``reason``,仍写到 events.jsonl
(append-only sink),但被 StepTreeAccumulatorDeriver 跳过。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from lca.infrastructure.observability.spine.context import SpineContext
from lca.infrastructure.observability.spine.derivers.step_tree_accumulator import (
    StepTreeAccumulatorDeriver,
)
from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.orphan import (
    CANCEL_PRE_BOOT,
    ORPHAN_REASONS,
    STOP_BEFORE_STEP,
    mark_orphan,
)


def _make_event(**overrides: object) -> EventRecord:
    base: dict[str, object] = {
        "execution_point": "kernel.boot.start",
        "channel": "control",
        "span_id": "01HMABC",
        "parent_span_id": None,
        "sequence": 1,
        "epoch": 1,
        "causality_id": "sha256:abc",
        "outcome": None,
        "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        "when_corrected": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        "prev_event_hash": None,
        "run_id": "r1",
        "step_id": None,
        "payload": {"k": "v"},
    }
    base.update(overrides)
    return EventRecord(**base)  # type: ignore[arg-type]


def _bound_deriver(tmp_path: Path) -> StepTreeAccumulatorDeriver:
    SpineContext.set_run("r-orphan")
    return StepTreeAccumulatorDeriver(
        run_id="r-orphan",
        run_dir=tmp_path,
        agent_role="agt_orphan_test",
        strategy_key="solo",
        plan_ref="plan_orphan",
    )


def test_orphan_phase_skipped_by_step_tree_deriver(tmp_path: Path) -> None:
    """An orphan event must not affect the deriver's accumulated steps."""
    deriver = _bound_deriver(tmp_path)
    rec = _make_event(phase="orphan", reason=CANCEL_PRE_BOOT)
    assert rec.phase == "orphan"
    assert rec.reason == CANCEL_PRE_BOOT

    deriver.on_event(rec)

    deriver.flush()
    # orphan event 不被累积 → journal.json 存在(空 document),但没有 step
    doc = deriver.document
    assert doc is not None
    assert len(doc.steps) == 0, "orphan event should not be accumulated as a step"


def test_orphan_requires_reason() -> None:
    """EventRecord(phase='orphan') 无 reason 必须抛错。"""
    with pytest.raises(ValueError, match="orphan events MUST carry reason"):
        _make_event(phase="orphan", reason=None)

    rec = _make_event(phase="orphan", reason=STOP_BEFORE_STEP)
    assert rec.phase == "orphan"
    assert rec.reason == STOP_BEFORE_STEP


def test_mark_orphan_helper() -> None:
    """mark_orphan 返回冻结副本,标 orphan + reason。"""
    live = _make_event()
    assert live.phase == "live"
    assert live.reason is None

    tagged = mark_orphan(live, CANCEL_PRE_BOOT)
    assert tagged.phase == "orphan"
    assert tagged.reason == CANCEL_PRE_BOOT
    assert live.phase == "live"
    assert live.reason is None
    assert tagged.execution_point == live.execution_point
    assert tagged.span_id == live.span_id
    assert tagged.sequence == live.sequence
    assert tagged.causality_id == live.causality_id


def test_mark_orphan_rejects_already_orphan() -> None:
    """mark_orphan 不能重复 tag orphan 记录。"""
    rec = _make_event(phase="orphan", reason=CANCEL_PRE_BOOT)
    with pytest.raises(ValueError, match="already phase='orphan'"):
        mark_orphan(rec, CANCEL_PRE_BOOT)


def test_orphan_reason_enum_is_closed() -> None:
    """ORPHAN_REASONS 是封闭枚举。"""
    assert (
        frozenset(
            {
                "cancel_pre_boot",
                "stop_before_step",
                "fail_before_step",
                "pending_tool_call",
                "panic",
            }
        )
        == ORPHAN_REASONS
    )
