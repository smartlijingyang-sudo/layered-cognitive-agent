"""fold_step_tree 纯函数 + StepTreeFoldDeriver facade 单测。

step 边界由 ``llm.request.header`` 唯一驱动(SSOT);fold 只从 spine
单源 fold,journal.json 是 spine 的派生面。
"""

from __future__ import annotations

import json
from pathlib import Path

from lca.plugins.session.derivers.step_tree import (
    StepTreeFoldDeriver,
    derive_step_tree,
)
from lca.plugins.session.derivers.step_tree.journal_fold import fold_step_tree

# ── fold_step_tree 纯函数 ────────────────────────────────────────


def _hdr(sid: str, when: int = 1_000, **extra: object) -> dict[str, object]:
    """构造一条 llm.request.header 事件(SSOT step 边界)。"""
    payload: dict[str, object] = {"step_id": sid}
    payload.update(extra)
    return {"execution_point": "llm.request.header", "payload": payload, "when": when}


def _phase_fold(kind: str, when: int, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {}
    payload.update(extra)
    return {"execution_point": f"phase.{kind}.fold", "payload": payload, "when": when}


def test_fold_empty_events_returns_empty_document() -> None:
    """空事件流 fold 出 0-step document。"""
    doc = fold_step_tree([], run_id="r_empty")
    assert doc.run_id == "r_empty"
    assert doc.schema == "lca.journal/3.1"
    assert len(doc.steps) == 0
    assert doc.totals is not None
    assert doc.totals.steps == 0


def test_single_llm_request_header_makes_one_step() -> None:
    """1 条 llm.request.header(step-001)→ 1 step。"""
    events = [
        _hdr("step-001"),
        _phase_fold("think", when=1_001),
    ]
    doc = fold_step_tree(events, run_id="r1")
    assert len(doc.steps) == 1
    assert doc.steps[0].step_id == "step-001"
    assert doc.totals is not None
    assert doc.totals.steps == 1


def test_phase_fold_creates_phase_record_without_step() -> None:
    """phase.<x>.fold 无 step 边界 → 0 step,phase 计数 ≥ 1。"""
    events = [_phase_fold("think", when=1_000, summary="thinking")]
    doc = fold_step_tree(events, run_id="r_phase")
    assert doc.totals is not None
    assert doc.totals.steps == 0
    assert doc.totals.phases >= 1
    assert any(p.kind == "think" for p in doc.phases)


def test_multi_round_llm_request_header_no_duplicate_step_id() -> None:
    """多轮 llm.request.header → N 步,step_id 严格唯一(SSOT 回归锁)。"""
    events = []
    for i in range(3):
        sid = f"step-{i + 1:03d}"
        events.extend(
            [
                _hdr(sid, when=1_000 + i * 100),
                _phase_fold("think", when=1_000 + i * 100 + 1),
            ]
        )
    doc = fold_step_tree(events, run_id="r_multi")
    assert len(doc.steps) == 3
    step_ids = [s.step_id for s in doc.steps]
    assert len(step_ids) == len(set(step_ids)), f"duplicate step_id: {step_ids}"
    assert step_ids == ["step-001", "step-002", "step-003"]
    assert [s.step_index for s in doc.steps] == [1, 2, 3]


def test_phase_fold_attaches_segment_to_open_step() -> None:
    """step 打开期间 phase.think.fold → step.segments 与 totals.segments 同步。"""
    events = [
        _hdr("step-001"),
        _phase_fold("think", when=1_001, summary="respond"),
    ]
    doc = fold_step_tree(events, run_id="r_seg")
    assert doc.totals is not None
    assert doc.totals.steps == 1
    assert doc.totals.segments == 1
    assert len(doc.steps[0].segments) == 1


def test_terminal_outcome_from_kernel_run_stop() -> None:
    """kernel.run.stop outcome=success → metadata.outcome='completed'。"""
    events = [
        {"execution_point": "kernel.run.stop", "payload": {}, "outcome": "success", "when": 0.0}
    ]
    doc = fold_step_tree(events, run_id="r_term")
    assert doc.metadata.outcome == "completed"


def test_explicit_outcome_overrides_spine() -> None:
    """显式 outcome 参数覆盖 spine 推导。"""
    events = [
        {"execution_point": "kernel.run.stop", "payload": {}, "outcome": "success", "when": 0.0}
    ]
    doc = fold_step_tree(events, run_id="r_override", outcome="failed")
    assert doc.metadata.outcome == "failed"


def test_tool_call_record_attaches_to_open_step() -> None:
    """step.tool_call.record → 当前 open_step.tool_call 非空。"""
    events = [
        _hdr("step-001"),
        {
            "execution_point": "step.tool_call.record",
            "payload": {
                "tool_name": "executeCode",
                "invocation_id": "inv_1",
                "arguments": {"code": "print(1)"},
                "arguments_summary": "executeCode(python)",
            },
            "when": 1_001,
        },
        _phase_fold("think", when=1_002),
    ]
    doc = fold_step_tree(events, run_id="r_tool")
    assert len(doc.steps) == 1
    tc = doc.steps[0].tool_call
    assert tc is not None
    assert tc.name == "executeCode"
    assert tc.invocation_id == "inv_1"


def test_unknown_ep_skipped() -> None:
    """未知 EP 被 skip,不中断 fold。"""
    events = [
        {"execution_point": "some.random.ep", "payload": {}, "when": 0.0},
        _hdr("step-001"),
        _phase_fold("think", when=1_001),
    ]
    doc = fold_step_tree(events, run_id="r_skip")
    assert doc.totals is not None
    assert doc.totals.steps == 1


# ── StepTreeFoldDeriver facade ───────────────────────────────────


def test_deriver_writes_journal_json(tmp_path: Path) -> None:
    """derive() 写 journal.json + document 可读。"""
    events = [_hdr("step-001"), _phase_fold("think", when=1_001)]
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
    events = [_phase_fold("think", when=1_000, summary="thinking")]
    doc = derive_step_tree(events, run_id="r_fn", run_dir=tmp_path, outcome="completed")

    journal = json.loads((tmp_path / "journal.json").read_text(encoding="utf-8"))
    assert journal["run_id"] == "r_fn"
    assert doc.totals is not None
    assert doc.totals.phases == 1


def test_fold_metadata_passthrough() -> None:
    """metadata 字段透传。"""
    doc = fold_step_tree(
        [],
        run_id="r_meta",
        agent_role="assistant",
        strategy_key="s1",
        plan_ref="abc",
        objective="do thing",
    )
    assert doc.metadata.agent_role == "assistant"
    assert doc.metadata.strategy_key == "s1"
    assert doc.metadata.plan_ref == "abc"


def test_deriver_reads_only_spine(tmp_path: Path) -> None:
    """fold 仅从 spine ledger 读(SSOT);session snapshot 不再优先。"""
    spine_path = tmp_path / "r.spine.jsonl"
    spine_path.write_text(
        "\n".join(
            json.dumps(ev)
            for ev in [
                _hdr("step-001"),
                _phase_fold("think", when=1_001),
            ]
        )
        + "\n"
    )

    # 即便传入 session,fold 也只从 spine 读
    deriver = StepTreeFoldDeriver(run_id="r", run_dir=tmp_path, spine_path=spine_path)
    deriver.flush()
    doc = deriver.document
    assert doc is not None
    assert doc.totals is not None
    assert doc.totals.steps == 1
    assert doc.steps[0].step_id == "step-001"
