"""Tests for PR-6 orphan-event semantics (ADR-0165.1 §19, design §4.3)。

orphan events 携带 ``phase="orphan"`` + ``reason``,仍写到 spine.jsonl
(append-only sink),但被 step_tree fold 跳过(ADR-0212 收口后:fold
不再持有 mutable 累积;orphan 事件经 `_coerce` 仍以 dict 形式进入 fold
但 fold 的 step 闭集不消费 phase='orphan' 的事件,因此 closed_frames 空)。

折叠路径收口后(ADR-0212)改走 :func:`fold_step_tree` 验证不变量等价。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from lca.infrastructure.observability.spine.event.record import EventRecord
from lca.infrastructure.observability.spine.orphan.orphan import (
    CANCEL_PRE_BOOT,
    ORPHAN_REASONS,
    STOP_BEFORE_STEP,
    mark_orphan,
)
from lca.plugins.session.derivers.step_tree.journal_fold import fold_step_tree


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
        "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC),
        "when_corrected": datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC),
        "prev_event_hash": None,
        "run_id": "r1",
        "step_id": None,
        "payload": {"k": "v"},
    }
    base.update(overrides)
    return EventRecord(**base)  # type: ignore[arg-type]


def test_orphan_phase_skipped_by_step_tree_fold(tmp_path: Path) -> None:
    """orphan event 不应被 fold 当成 step 累积(ADR-0212 收口后 fold SSOT)。"""
    rec = _make_event(phase="orphan", reason=CANCEL_PRE_BOOT)
    assert rec.phase == "orphan"
    assert rec.reason == CANCEL_PRE_BOOT

    doc = fold_step_tree([rec], run_id="r-orphan")
    # orphan event 不被累积 → doc 存在(空 steps),但没有 step 帧
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
