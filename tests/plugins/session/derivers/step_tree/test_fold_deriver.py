"""fold_step_tree 纯函数 + StepTreeFoldDeriver facade 单测(PRD-3g 样本)。

覆盖:
- fold_step_tree: 从 dict 事件流 fold 出 JournalDocument
- StepTreeFoldDeriver: derive 写 journal.json + document 可读
- derive_step_tree: 一次性 fold + 写盘
- 与旧 StepTreeAccumulatorDeriver 语义等价(fold 路径 vs callback 路径)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from lca.plugins.session.derivers.step_tree import (
    StepTreeFoldDeriver,
    derive_step_tree,
)
from lca.plugins.session.derivers.step_tree.journal_fold import fold_step_tree

# ── fold_step_tree 纯函数 ────────────────────────────────────────


def test_fold_empty_events_returns_empty_document() -> None:
    """空事件流 fold 出 0-step document。"""
    doc = fold_step_tree([], run_id="r_empty")
    assert doc.run_id == "r_empty"
    assert doc.schema == "lca.journal/3.1"
    assert len(doc.steps) == 0
    assert doc.totals is not None
    assert doc.totals.steps == 0


def test_fold_single_step_from_writable_events() -> None:
    """writable.step.start + writable.step.end → 1 step。"""
    events = [
        {
            "execution_point": "writable.step.start",
            "payload": {"phase": "think"},
            "outcome": None,
            "phase": "live",
            "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        },
        {
            "execution_point": "writable.step.end",
            "payload": {"outcome": "success"},
            "outcome": "success",
            "phase": "live",
            "when": datetime(2026, 9, 1, 12, 0, 1, tzinfo=timezone.utc),
        },
    ]
    doc = fold_step_tree(events, run_id="r1")
    assert len(doc.steps) == 1
    assert doc.steps[0].phase == "think"
    assert doc.steps[0].outcome == "success"
    assert doc.totals is not None
    assert doc.totals.steps == 1


def test_fold_brain_think_start_end_creates_implicit_step() -> None:
    """brain.think.start/end → 隐式 step(backend ReAct 路径)。"""
    events = [
        {
            "execution_point": "brain.think.start",
            "payload": {},
            "outcome": None,
            "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        },
        {
            "execution_point": "brain.think.end",
            "payload": {},
            "outcome": "success",
            "when": datetime(2026, 9, 1, 12, 0, 1, tzinfo=timezone.utc),
        },
    ]
    doc = fold_step_tree(events, run_id="r_implicit")
    assert doc.totals is not None
    assert doc.totals.steps == 1
    assert doc.steps[0].outcome == "success"


def test_fold_phase_fold_creates_phase_record() -> None:
    """phase.think.fold → PhaseRecord(kind='think')。"""
    events = [
        {
            "execution_point": "phase.think.fold",
            "payload": {"summary": "thinking"},
            "outcome": None,
            "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        },
    ]
    doc = fold_step_tree(events, run_id="r_phase")
    assert doc.totals is not None
    assert doc.totals.phases >= 1
    assert any(p.kind == "think" for p in doc.phases)


def test_fold_terminal_outcome_from_kernel_run_stop() -> None:
    """kernel.run.stop outcome=success → metadata.outcome='completed'。"""
    events = [
        {
            "execution_point": "kernel.run.stop",
            "payload": {},
            "outcome": "success",
            "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        },
    ]
    doc = fold_step_tree(events, run_id="r_term")
    assert doc.metadata.outcome == "completed"


def test_fold_explicit_outcome_overrides_spine() -> None:
    """显式 outcome 参数覆盖 spine 推导。"""
    events = [
        {
            "execution_point": "kernel.run.stop",
            "payload": {},
            "outcome": "success",
            "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        },
    ]
    doc = fold_step_tree(events, run_id="r_override", outcome="failed")
    assert doc.metadata.outcome == "failed"


def test_fold_tool_call_record_attaches_to_step() -> None:
    """step.tool_call.record flat payload → step.tool_call 非空。"""
    events = [
        {
            "execution_point": "writable.step.start",
            "payload": {"phase": "act"},
            "outcome": None,
            "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        },
        {
            "execution_point": "step.tool_call.record",
            "payload": {
                "tool_name": "executeCode",
                "invocation_id": "inv_1",
                "arguments": {"code": "print(1)"},
                "arguments_summary": "executeCode(python)",
                "step_index": 1,
            },
            "outcome": None,
            "when": datetime(2026, 9, 1, 12, 0, 1, tzinfo=timezone.utc),
        },
        {
            "execution_point": "writable.step.end",
            "payload": {},
            "outcome": "success",
            "when": datetime(2026, 9, 1, 12, 0, 2, tzinfo=timezone.utc),
        },
    ]
    doc = fold_step_tree(events, run_id="r_tool")
    assert len(doc.steps) == 1
    tc = doc.steps[0].tool_call
    assert tc is not None
    assert tc.name == "executeCode"
    assert tc.invocation_id == "inv_1"


def test_fold_skips_unrecognized_events() -> None:
    """未知 EP 被 skip,不中断 fold。"""
    events = [
        {"execution_point": "some.random.ep", "payload": {}, "when": 0.0},
        {
            "execution_point": "writable.step.start",
            "payload": {"phase": "think"},
            "outcome": None,
            "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        },
        {
            "execution_point": "writable.step.end",
            "payload": {},
            "outcome": "success",
            "when": datetime(2026, 9, 1, 12, 0, 1, tzinfo=timezone.utc),
        },
    ]
    doc = fold_step_tree(events, run_id="r_skip")
    assert doc.totals is not None
    assert doc.totals.steps == 1


# ── StepTreeFoldDeriver facade ───────────────────────────────────


def test_deriver_writes_journal_json(tmp_path: Path) -> None:
    """derive() 写 journal.json + document 可读。"""
    events = [
        {
            "execution_point": "writable.step.start",
            "payload": {"phase": "think"},
            "outcome": None,
            "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        },
        {
            "execution_point": "writable.step.end",
            "payload": {},
            "outcome": "success",
            "when": datetime(2026, 9, 1, 12, 0, 1, tzinfo=timezone.utc),
        },
    ]
    deriver = StepTreeFoldDeriver(run_id="r_derive", run_dir=tmp_path)
    doc = deriver.derive(events)

    assert (tmp_path / "journal.json").exists()
    assert deriver.document is not None
    assert deriver.document.run_id == "r_derive"
    assert doc.totals is not None
    assert doc.totals.steps == 1


def test_deriver_flush_writes_empty_document(tmp_path: Path) -> None:
    """flush() 无 events 时写空 document。"""
    deriver = StepTreeFoldDeriver(run_id="r_flush", run_dir=tmp_path, outcome="completed")
    deriver.flush()

    assert (tmp_path / "journal.json").exists()
    assert deriver.document is not None
    assert deriver.document.metadata.outcome == "completed"


def test_derive_step_tree_function(tmp_path: Path) -> None:
    """derive_step_tree 一次性函数写 journal.json。"""
    events = [
        {
            "execution_point": "phase.think.fold",
            "payload": {"summary": "thinking"},
            "outcome": None,
            "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        },
    ]
    doc = derive_step_tree(events, run_id="r_fn", run_dir=tmp_path, outcome="completed")

    journal = json.loads((tmp_path / "journal.json").read_text(encoding="utf-8"))
    assert journal["run_id"] == "r_fn"
    assert journal["schema"] == "lca.journal/3.1"
    assert doc.metadata.outcome == "completed"
    assert doc.totals is not None
    assert doc.totals.phases >= 1


def test_fold_metadata_passthrough() -> None:
    """agent_role / plan_ref / objective 写入 JournalMetadata。"""
    doc = fold_step_tree(
        [],
        run_id="r_meta",
        outcome="completed",
        agent_role="coder",
        strategy_key="solo",
        plan_ref="abcd1234abcd1234",
        objective="ship fold path",
    )
    assert doc.metadata.agent_role == "coder"
    assert doc.metadata.strategy_key == "solo"
    assert doc.metadata.plan_ref == "abcd1234abcd1234"
    assert doc.metadata.objective == "ship fold path"
    assert doc.metadata.outcome == "completed"


def test_fold_iso_when_and_session_event() -> None:
    """ISO when 字符串 + SessionEvent 信封都能 fold 出 step。"""
    from lca_kernel.events.session import SessionEvent

    events = [
        {
            "execution_point": "writable.step.start",
            "payload": {"phase": "think"},
            "when": "2026-09-01T12:00:00+00:00",
        },
        SessionEvent(
            type="writable.step.end",
            seq=1,
            time=1_756_728_001_000,
            data={"outcome": "success"},
        ),
    ]
    doc = fold_step_tree(events, run_id="r_coerce")
    assert len(doc.steps) == 1
    assert doc.steps[0].outcome == "success"
    assert doc.steps[0].duration_ms is not None
    assert doc.steps[0].duration_ms >= 0


def test_deriver_flush_from_spine_reader(tmp_path: Path) -> None:
    """flush 从 SpineReader 读 spine.jsonl 再 fold 写 journal.json。"""
    run_id = "r_flush_spine"
    spine_path = tmp_path / f"{run_id}.spine.jsonl"
    events = [
        {
            "execution_point": "writable.step.start",
            "payload": {"phase": "think"},
            "outcome": None,
            "when": "2026-09-01T12:00:00+00:00",
        },
        {
            "execution_point": "writable.step.end",
            "payload": {},
            "outcome": "success",
            "when": "2026-09-01T12:00:01+00:00",
        },
    ]
    spine_path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )
    deriver = StepTreeFoldDeriver(
        run_id=run_id,
        run_dir=tmp_path,
        spine_path=spine_path,
        objective="flush from spine",
    )
    deriver.flush(outcome="completed")

    assert (tmp_path / "journal.json").exists()
    assert deriver.document is not None
    assert deriver.document.metadata.outcome == "completed"
    assert deriver.document.metadata.objective == "flush from spine"
    assert deriver.document.totals is not None
    assert deriver.document.totals.steps == 1


def test_deriver_flush_prefers_session_snapshot(tmp_path: Path) -> None:
    """Session.snapshot_events 优先于 SpineReader。"""
    from lca.plugins.session.runtime.session import Session

    session = Session("r_sess")
    session.append("writable.step.start", {"phase": "act"})
    session.append("writable.step.end", {"outcome": "success"})
    # 盘上若有平行 spine,也必须被忽略。
    spine_path = tmp_path / "r_sess.spine.jsonl"
    spine_path.write_text(
        json.dumps(
            {
                "execution_point": "writable.step.start",
                "payload": {"phase": "think"},
                "when": "2026-09-01T12:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    deriver = StepTreeFoldDeriver(
        run_id="r_sess",
        run_dir=tmp_path,
        spine_path=spine_path,
        session=session,
    )
    deriver.flush(outcome="completed")
    assert deriver.document is not None
    assert deriver.document.totals is not None
    assert deriver.document.totals.steps == 1
    assert deriver.document.steps[0].phase == "act"


def test_step_tree_bundle_flush_passes_outcome(tmp_path: Path) -> None:
    """_StepTreeBundle.flush 把 outcome 传给 fold deriver 并写 narrative。"""
    from lca.plugins.observability.run_ledger_seam import _StepTreeBundle

    class _Narrative:
        def __init__(self) -> None:
            self.docs: list[object] = []

        def write(self, document: object) -> None:
            self.docs.append(document)

    spine_path = tmp_path / "r_bundle.spine.jsonl"
    spine_path.write_text(
        json.dumps(
            {
                "execution_point": "kernel.run.stop",
                "payload": {},
                "outcome": "success",
                "when": "2026-09-01T12:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    deriver = StepTreeFoldDeriver(
        run_id="r_bundle",
        run_dir=tmp_path,
        spine_path=spine_path,
    )
    narrative = _Narrative()
    bundle = _StepTreeBundle(deriver=deriver, narrative_writer=narrative)
    bundle.flush(outcome="failed")

    assert (tmp_path / "journal.json").exists()
    assert deriver.document is not None
    assert deriver.document.metadata.outcome == "failed"
    assert narrative.docs == [deriver.document]
