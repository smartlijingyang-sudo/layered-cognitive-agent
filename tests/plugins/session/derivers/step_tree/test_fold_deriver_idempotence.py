"""StepTreeFoldDeriver 幂等 / 失败可见 / spine 重放回归 (ADR-0212 §6)。

覆盖:
- 同 events 两次 fold → 同 JournalDocument(C9 幂等 / 重入);
- 写盘失败 → :class:`JournalWriteError` typed exception(不 swallow);
- spine 重放 fold = 单次 fold(回归 run_f78f66322f1d 的 doctor H3 重复 step_id);
- 平移原 test_observation_ssot_regression.py 的 3 个 fold 测试:
  tool_call canonical payload 恢复 / nested fallback / act.fold after step close
  (回归 run_3e48052e6c36 + run_6f2b73a32d32)。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lca.contracts.observability.journal.errors import JournalWriteError
from lca.infrastructure.observability.journal.step.reader import read_step_document
from lca.plugins.session.derivers.step_tree import (
    StepTreeFoldDeriver,
    derive_step_tree,
)
from lca.plugins.session.derivers.step_tree.journal_fold import fold_step_tree


def _ts(year: int, month: int, day: int, hour: int = 12, minute: int = 0, second: int = 0):
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


def _make_event(*, ep: str, payload: dict | None = None, outcome: str | None = None, when: int = 1):
    """dict-style fold input,与 ``test_fold_deriver.py`` 风格一致。"""
    return {
        "execution_point": ep,
        "payload": payload or {},
        "outcome": outcome,
        "phase": "live",
        "when": _ts(2026, 9, 9, when),
    }


# ── 1. C9 幂等 / 重入 ──────────────────────────────────────────


def test_repeat_derive_writes_identical_journal(tmp_path: Path) -> None:
    """同 events + 同 outcome 两次 fold → 同 JournalDocument(ADR-0212 §5.3)。"""
    spine_events = [
        _make_event(ep="writable.step.start", payload={"step_id": "step-001", "step": 1, "phase": "perceive"}, when=1),
        _make_event(ep="phase.think.fold", payload={"step_index": 1, "phase": "think", "objective": "thinking", "objective_kind": "user_text"}, when=2),
        _make_event(ep="brain.think.end", outcome="success", when=3),
        _make_event(ep="writable.step.start", payload={"step_id": "step-002", "step": 2, "phase": "perceive"}, when=4),
        _make_event(ep="phase.think.fold", payload={"step_index": 2, "phase": "think", "objective": "thinking 2", "objective_kind": "user_text"}, when=5),
        _make_event(ep="brain.think.end", outcome="success", when=6),
    ]
    run_dir = tmp_path / "r_idem"
    d1 = StepTreeFoldDeriver("r_idem", run_dir).derive(spine_events)
    d2 = StepTreeFoldDeriver("r_idem", run_dir).derive(spine_events)
    assert d1.steps == d2.steps
    assert [s.step_id for s in d1.steps] == ["step-001", "step-002"]


def test_flush_after_derive_is_idempotent(tmp_path: Path) -> None:
    """flush() 第二次调用幂等(同 events 同 outcome)。"""
    spine_events = [
        _make_event(ep="writable.step.start", payload={"step_id": "step-001", "step": 1, "phase": "perceive"}, when=1),
        _make_event(ep="brain.think.end", outcome="success", when=2),
    ]
    run_dir = tmp_path / "r_flush_idem"
    deriver = StepTreeFoldDeriver("r_flush_idem", run_dir)
    deriver.derive(spine_events)
    initial_doc = deriver.document
    deriver.flush()
    reread = read_step_document(run_dir / "journal.json")
    assert reread.steps == initial_doc.steps


# ── 2. C11 失败可见 ───────────────────────────────────────────


def test_write_failure_raises_typed_exception(tmp_path: Path) -> None:
    """写盘失败不再 swallow,而是 raise :class:`JournalWriteError`(ADR-0212 §5.2)。"""
    deriver = StepTreeFoldDeriver("r_fail", tmp_path)
    # 制造不可写状态:把 journal.json 做成 read-only 子目录(tmp_path 整体 chmod)。
    (tmp_path / "journal.json").write_text("placeholder")
    tmp_path.chmod(0o555)
    try:
        events = [_make_event(ep="writable.step.start", payload={"step_id": "step-001", "step": 1, "phase": "perceive"}, when=1)]
        with pytest.raises(JournalWriteError) as exc_info:
            deriver.derive(events)
        assert exc_info.value.run_id == "r_fail"
        assert exc_info.value.target == tmp_path / "journal.json"
        assert exc_info.value.__cause__ is not None
    finally:
        tmp_path.chmod(0o755)


def test_derive_step_tree_raises_typed_exception(tmp_path: Path) -> None:
    """``derive_step_tree`` 一次性函数同样 fail-loud(ADR-0212 §5.2 全覆盖)。"""
    (tmp_path / "journal.json").write_text("placeholder")
    tmp_path.chmod(0o555)
    try:
        events = [_make_event(ep="writable.step.start", payload={"step_id": "step-001", "step": 1, "phase": "perceive"}, when=1)]
        with pytest.raises(JournalWriteError):
            derive_step_tree(events, run_id="r_fail_2", run_dir=tmp_path)
    finally:
        tmp_path.chmod(0o755)


# ── 3. run_f78f66322f1d 回归(doctor H3 duplicate step_id) ──────


def test_spine_replay_equals_single_fold_no_duplicate_step_id(tmp_path: Path) -> None:
    """回归 run_f78f66322f1d:spine 重放 fold 只产 2 步,无重复 step_id。

    原 run 因写入侧失败留下 stale journal.json(step-001 重复 2 次),
    fold 逻辑正确。ADR-0212 §6 锁这条锁:同 spine 重放必须等于单次 fold。
    """
    spine_path = Path("traces/runs/run_f78f66322f1d/run_f78f66322f1d.spine.jsonl")
    if not spine_path.exists():
        pytest.skip("run_f78f66322f1d spine ledger not on disk")

    raw_events = [json.loads(line) for line in spine_path.read_text().splitlines() if line.strip()]
    doc = fold_step_tree(raw_events, run_id="run_f78f66322f1d")

    step_ids = [s.step_id for s in doc.steps]
    assert len(step_ids) == len(set(step_ids)), f"duplicate step_id in {step_ids}"
    assert step_ids == ["step-001", "step-002"]
    assert [s.step_index for s in doc.steps] == [1, 2]


# ── 4. 平移原 test_observation_ssot_regression.py fold 测试 ──────


def test_step_tree_records_tool_call_from_canonical_payload(tmp_path: Path) -> None:
    """fold 从 canonical flat payload 恢复 ``ToolCallRecord``(回归 run_3e48052e6c36)。

    原 test_observation_ssot_regression.py 第 2 节;ADR-0212 后改为
    ``derive_step_tree`` 一次性 fold + 读 journal.json 验证。
    """
    events = [
        _make_event(ep="writable.step.start", payload={"phase": "act", "step_id": "step_001"}, when=1),
        _make_event(
            ep="step.tool_call.record",
            payload={
                "tool_name": "executeCode",
                "call_seq": 7,
                "invocation_id": "inv-001",
                "arguments": {"code": "print('hi')"},
                "arguments_summary": 'code="print(\'hi\')"',
                "incarnation": 1,
                "plan_ref": "plan_test",
                "step_index": 1,
            },
            when=2,
        ),
        _make_event(
            ep="step.tool_result.record",
            payload={
                "tool_name": "executeCode",
                "result_digest": "sha256:def",
                "result_path": None,
                "outcome": "ok",
                "invocation_id": "inv-001",
                "ok": True,
                "latency_ms": 240,
                "stdout_head": "hi\n",
                "stderr": "",
                "files_created": ("out.txt",),
                "error": None,
                "delta_summary": "✅ stdout[:80] = hi",
            },
            when=3,
        ),
        _make_event(ep="writable.step.end", payload={"step_id": "step_001"}, outcome="success", when=4),
    ]
    run_dir = tmp_path / "r_tc"
    derive_step_tree(events, run_id="r_tc", run_dir=run_dir, plan_ref="plan_test", agent_role="agt_test", strategy_key="solo")

    doc = read_step_document(run_dir / "journal.json")
    assert len(doc.steps) == 1, f"expected 1 step, got {len(doc.steps)}"
    step = doc.steps[0]
    assert step.tool_call is not None, "tool_call missing"
    assert step.tool_call.name == "executeCode"
    assert step.tool_call.invocation_id == "inv-001"
    assert step.tool_call.arguments == {"code": "print('hi')"}
    assert step.tool_call.arguments_summary == 'code="print(\'hi\')"'

    assert step.tool_result is not None, "tool_result missing"
    assert step.tool_result.ok is True
    assert step.tool_result.latency_ms == 240
    assert step.tool_result.stdout_head == "hi\n"
    assert step.tool_result.files_created == ("out.txt",)
    assert step.tool_result.delta_summary == "✅ stdout[:80] = hi"


def test_step_tree_records_tool_call_canonical_only(tmp_path: Path) -> None:
    """fold binding engine 只消费 canonical flat payload,``payload.call.*`` nested 已被 ADR-0212 收口下线。

    历史:旧 fold deriver 的 ``_apply`` 手写过 nested fallback
    (从 ``payload.call.*`` 兜底);该 deriver 已物理删除,fold binding
    rule 仅声明 canonical(见 ``journal_step_tree.yaml``)。
    若未来重新引入 nested fallback,需先扩展 binding rule + ADR,见
    ADR-0212 §6 替代路径。
    """
    events = [
        _make_event(ep="writable.step.start", payload={"phase": "act", "step_id": "step_001"}, when=1),
        _make_event(
            ep="step.tool_call.record",
            payload={
                "call": {
                    "invocation_id": "inv-nested",
                    "name": "legacy_tool",
                    "arguments": {"x": 1},
                    "arguments_summary": "x=1",
                },
                "tool_name": "modern_tool",
            },
            when=2,
        ),
        _make_event(ep="writable.step.end", payload={"step_id": "step_001"}, outcome="success", when=3),
    ]
    run_dir = tmp_path / "r_nest"
    derive_step_tree(events, run_id="r_nest", run_dir=run_dir, plan_ref="plan", agent_role="agt", strategy_key="solo")
    doc = read_step_document(run_dir / "journal.json")
    assert len(doc.steps) == 1
    step = doc.steps[0]
    assert step.tool_call is not None
    assert step.tool_call.name == "modern_tool"
    # nested invocation_id 不被 binding engine 拾取(规则只读 canonical)
    assert step.tool_call.invocation_id == ""
    assert step.tool_call.arguments == {}


def test_phase_act_fold_after_step_close_attaches_to_closed_step(tmp_path: Path) -> None:
    """``brain.think.end`` 之后到达的 ``phase.act.fold`` 必须 attach 到刚 close 的 step。

    回归 run_6f2b73a32d32:"totals.segments=8 但 sum(steps.segments)=6"
    直接根因。
    """
    events = [
        _make_event(ep="brain.think.start", payload={"state_id": "x"}, when=1),
        _make_event(ep="phase.think.fold", payload={"phase": "think", "summary": "t1", "objective": "", "objective_kind": "system_role"}, when=2),
        _make_event(ep="phase.think.fold", payload={"phase": "think", "summary": "t2", "objective": "", "objective_kind": "system_role"}, when=3),
        _make_event(ep="phase.think.fold", payload={"phase": "think", "summary": "t3", "objective": "", "objective_kind": "system_role"}, when=4),
        _make_event(ep="brain.think.end", payload={"state_id": "x"}, outcome="success", when=5),
        # orphan-arrival:brain.think.end 之后
        _make_event(ep="phase.act.fold", payload={"phase": "act", "summary": "orphan-act", "objective": "", "objective_kind": "system_role"}, when=6),
    ]
    run_dir = tmp_path / "r_hseg"
    derive_step_tree(events, run_id="r_hseg", run_dir=run_dir, plan_ref="plan", agent_role="agt", strategy_key="solo")
    doc = read_step_document(run_dir / "journal.json")

    assert len(doc.steps) == 1, f"expected 1 step, got {len(doc.steps)}"
    step = doc.steps[0]
    seg_kinds = [seg.kind for seg in step.segments]
    assert seg_kinds.count("think") == 3, f"expected 3 think segs, got {seg_kinds.count('think')}"
    assert seg_kinds.count("act") == 1, (
        f"act.fold must attach to closed step, got segs={seg_kinds}"
    )

    # H-seg 不变量:sum(steps.segments) == totals.segments
    sum_segs = sum(len(s.segments) for s in doc.steps)
    assert sum_segs == doc.totals.segments, (
        f"H-seg 不一致:sum(steps.segments)={sum_segs} != totals.segments={doc.totals.segments}"
    )
