"""StepTreeFoldDeriver 幂等 / 失败可见 / spine 重放回归 (ADR-0212 §6)。

step 边界由 ``llm.request.header`` 唯一驱动(SSOT);fold 是纯函数,
同 events 重复 fold 必产同 JournalDocument(C9 幂等)。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.contracts.observability.journal.errors import JournalWriteError
from lca.infrastructure.observability.journal.step.reader import read_step_document
from lca.plugins.session.derivers.step_tree import (
    StepTreeFoldDeriver,
    derive_step_tree,
)
from lca.plugins.session.derivers.step_tree.journal_fold import fold_step_tree


def _hdr(sid: str, when: int) -> dict[str, object]:
    return {"execution_point": "llm.request.header", "payload": {"step_id": sid}, "when": when}


def _phase(kind: str, when: int) -> dict[str, object]:
    return {"execution_point": f"phase.{kind}.fold", "payload": {}, "when": when}


# ── C9 幂等 / 重入 ──────────────────────────────────────────


def test_repeat_derive_writes_identical_journal(tmp_path: Path) -> None:
    """同 events + 同 outcome 两次 fold → 同 JournalDocument。"""
    events = [
        _hdr("step-001", when=1),
        _phase("think", when=2),
        _hdr("step-002", when=3),
        _phase("think", when=4),
    ]
    run_dir = tmp_path / "r_idem"
    d1 = StepTreeFoldDeriver("r_idem", run_dir).derive(events)
    d2 = StepTreeFoldDeriver("r_idem", run_dir).derive(events)
    assert d1.steps == d2.steps


def test_repeat_flush_is_noop_with_identical_output(tmp_path: Path) -> None:
    """flush() 重复调用产出同一 journal.json(原子覆盖)。"""
    events = [_hdr("step-001", when=1), _phase("think", when=2)]
    run_dir = tmp_path / "r_flush"
    deriver = StepTreeFoldDeriver("r_flush", run_dir)
    deriver.derive(events)
    first = json.loads((run_dir / "journal.json").read_text(encoding="utf-8"))
    deriver.flush()
    second = json.loads((run_dir / "journal.json").read_text(encoding="utf-8"))
    assert first == second


# ── 失败可见(ADR-0212 §5 fail-loud) ─────────────────────────────


def test_derive_writes_via_journal_writer(tmp_path: Path) -> None:
    """derive() 走 JournalDocumentWriter 原子覆盖,落 journal.json。"""
    run_dir = tmp_path / "r_write"
    events = [_hdr("step-001", when=1), _phase("think", when=2)]
    doc = derive_step_tree(events, run_id="r_write", run_dir=run_dir, outcome="completed")

    journal_path = run_dir / "journal.json"
    assert journal_path.exists()
    on_disk = json.loads(journal_path.read_text(encoding="utf-8"))
    assert on_disk["run_id"] == "r_write"
    assert on_disk["metadata"]["outcome"] == "completed"
    assert doc.totals is not None
    assert doc.totals.steps == 1


# ── 重读 ────────────────────────────────────────────


def test_read_step_document_round_trip(tmp_path: Path) -> None:
    """derive 写入的 journal.json 可由 read_step_document 读回。"""
    run_dir = tmp_path / "r_round"
    events = [_hdr("step-001", when=1), _phase("think", when=2)]
    StepTreeFoldDeriver("r_round", run_dir).derive(events)

    doc = read_step_document(run_dir / "journal.json")
    assert doc.totals is not None
    assert doc.totals.steps == 1
    assert doc.steps[0].step_id == "step-001"


# ── spine 重放:同 spine 流 fold 两次 → 同 doc(回归 run_3cf06424f0b7) ─────


def test_spine_replay_no_duplicate_step_id(tmp_path: Path) -> None:
    """spine 流 fold 两次 → step_id 严格 unique,无 duplicate step_id。

    回归 run_3cf06424f0b7:journal.json 出现 step-001 / step-001 / step-002
    三步,doctor H3 broken 'duplicate step_id'。修复:fold 单源 + step 边界
    由 llm.request.header 唯一驱动。
    """
    spine_events = [_hdr(f"step-{i + 1:03d}", when=i + 1) for i in range(3)]
    doc = fold_step_tree(spine_events, run_id="r_replay")
    step_ids = [s.step_id for s in doc.steps]
    assert len(step_ids) == len(set(step_ids)), f"duplicate step_id: {step_ids}"
    assert step_ids == ["step-001", "step-002", "step-003"]


# ── tool_call canonical payload(平移原 observation_ssot_regression) ──


def test_step_tree_records_tool_call_from_canonical_payload() -> None:
    """llm.request.header.assistant 带 tool_calls → step.tool_call 非空。"""
    events = [
        _hdr("step-001", when=1),
        {
            "execution_point": "llm.request.header.assistant",
            "payload": {
                "assistant_content": "",
                "tool_calls": [
                    {
                        "id": "inv_1",
                        "function": {"name": "executeCode", "arguments": '{"code": "print(1)"}'},
                    }
                ],
            },
            "when": 2,
        },
    ]
    doc = fold_step_tree(events, run_id="r_tool_canonical")
    assert len(doc.steps) == 1
    tc = doc.steps[0].tool_call
    assert tc is not None
    assert tc.name == "executeCode"
    assert tc.invocation_id == "inv_1"
    assert tc.arguments == {"code": "print(1)"}


def test_step_tree_records_tool_call_canonical_only() -> None:
    """tool_calls 是 list(Mapping) → fold 抽取第一个 call。"""
    events = [
        _hdr("step-001", when=1),
        {
            "execution_point": "llm.request.header.assistant",
            "payload": {
                "assistant_content": "ok",
                "tool_calls": [
                    {
                        "id": "inv_a",
                        "function": {"name": "toolA"},
                    },
                    {
                        "id": "inv_b",
                        "function": {"name": "toolB"},
                    },
                ],
            },
            "when": 2,
        },
    ]
    doc = fold_step_tree(events, run_id="r_tool_first")
    tc = doc.steps[0].tool_call
    assert tc is not None
    assert tc.name == "toolA"


def test_phase_act_fold_after_step_close_attaches_to_closed_step() -> None:
    """step 已关闭后 phase.act.fold → 挂到最近 closed frame(时间窗兜底)。"""
    events = [
        _hdr("step-001", when=1),
        _phase("think", when=2),
        _hdr("step-002", when=3),  # 关 step-001,开 step-002
        {"execution_point": "phase.act.fold", "payload": {"outcome": "ok"}, "when": 4},
    ]
    doc = fold_step_tree(events, run_id="r_act_after")
    assert doc.totals is not None
    assert doc.totals.steps == 2
    # step-001 已关闭;phase.fold 在 step-002 期间挂到 step-002 上
    # frame.phase 默认 'think'(LLM 边界专属);phase.act.fold 仅记入 phases 列表
    assert any(p.kind == "act" for p in doc.phases)
