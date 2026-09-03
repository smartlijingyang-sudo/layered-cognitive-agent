"""观测面 SSOT 收口回归测试(2026-09-03)。

覆盖 docs/notes/implemented/seam/2026-09-03-observation-ssot-registry.md
根 note 收口的 4 个核心修复:

1. ``find_spine_file`` 优先 ``<run_dir>/<run_id>.spine.jsonl``,
   其次 ``<run_dir>/events.jsonl`` 兜底;两者都缺抛 ObservationSSOTError。
2. ``StepTreeAccumulatorDeriver._apply`` 处理 ``step.tool_call.record``
   时能从 canonical flat payload 恢复 ``ToolCallRecord.name`` /
   ``arguments`` / ``arguments_summary`` / ``invocation_id`` —— 这正是
   run_3e48052e6c36 那次 ``tool_call`` 全空、用户看不到 tool 名字的
   根因(verifiable on the shipped StepTreeAccumulatorDeriver)。
3. ``StepTreeAccumulatorDeriver._apply`` 处理 ``step.tool_result.record``
   时能从 canonical flat payload 恢复 ``stdout_head`` / ``stderr`` /
   ``files_created`` / ``error`` / ``delta_summary`` —— 这正是同次
   run ``tool_result`` 全空的根因。
4. ``RunOutcomeProjector.failed`` 在异常归一化前自动调用
   ``emit_exception_caught``,把 traceback 落到 ``exception.caught`` spine
   event,而不是只在 ``RunFact.payload["error"]`` 写一行字符串。

每条 test 直接驱动 shipped  code,not re-implementation。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from lca.contracts.models.core.state import AgentState, Budget
from lca.harness.declarative.execute.outcome_projection import RunOutcomeProjector
from lca.infrastructure.observability.journal.step.reader import read_step_document
from lca.infrastructure.observability.spine.context import SpineContext
from lca.infrastructure.observability.spine.derivers.step_tree_accumulator import (
    StepTreeAccumulatorDeriver,
)
from lca.infrastructure.observability.spine.event_record import EventRecord

# ── 1. find_spine_file (ssot.py) ────────────────────────────────────────


def test_find_spine_file_prefers_new_naming(tmp_path: Path) -> None:
    """新 spine 命名(``<run_id>.spine.jsonl``)存在 → 直接返回。"""
    from lca.contracts.observability.ssot import find_spine_file

    run_dir = tmp_path / "run_abc"
    run_dir.mkdir()
    new = run_dir / "run_abc.spine.jsonl"
    new.write_text("{}\n", encoding="utf-8")
    legacy = run_dir / "events.jsonl"
    legacy.write_text("{}\n", encoding="utf-8")
    # 两者并存:必须返回 spine 命名,而不是 legacy(PR-27 约定)。
    assert find_spine_file(run_dir, "run_abc") == new


def test_find_spine_file_legacy_fallback(tmp_path: Path) -> None:
    """新命名不存在但 events.jsonl 存在 → 返回 legacy。"""
    from lca.contracts.observability.ssot import find_spine_file

    run_dir = tmp_path / "run_abc"
    run_dir.mkdir()
    legacy = run_dir / "events.jsonl"
    legacy.write_text("{}\n", encoding="utf-8")
    assert find_spine_file(run_dir, "run_abc") == legacy


def test_find_spine_file_missing_both_raises(tmp_path: Path) -> None:
    """两者都缺 → ObservationSSOTError,不是 silent zero。"""
    from lca.contracts.observability.ssot import ObservationSSOTError, find_spine_file

    run_dir = tmp_path / "run_abc"
    run_dir.mkdir()
    with pytest.raises(ObservationSSOTError):
        find_spine_file(run_dir, "run_abc")


def test_find_spine_file_missing_run_dir_raises(tmp_path: Path) -> None:
    """run_dir 本身不存在 → ObservationSSOTError,file name 不存在仅是子集。"""
    from lca.contracts.observability.ssot import ObservationSSOTError, find_spine_file

    with pytest.raises(ObservationSSOTError):
        find_spine_file(tmp_path / "nope", "run_abc")


# ── 2. deriver reads canonical tool_call payload ────────────────────────


def _make_event(**overrides: object) -> EventRecord:
    base: dict[str, object] = {
        "execution_point": "writable.step.start",
        "channel": "control",
        "span_id": "01HM",
        "parent_span_id": None,
        "sequence": 1,
        "epoch": 1,
        "causality_id": "sha256:abc",
        "outcome": None,
        "when": datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc),
        "when_corrected": datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc),
        "prev_event_hash": None,
        "run_id": "r_tc",  # 由各测试在 overrides 里覆盖
        "step_id": "step_001",
        "phase": "live",
        "payload": {"phase": "act"},
    }
    base.update(overrides)
    return EventRecord(**base)  # type: ignore[arg-type]


def test_step_tree_records_tool_call_from_canonical_payload(tmp_path: Path) -> None:
    """deriver 必须从 ``payload.tool_name`` / ``payload.arguments`` /
    ``payload.arguments_summary`` / ``payload.invocation_id`` 恢复出
    完整 ``ToolCallRecord``。这是 run_3e48052e6c36 漏投影的直接根因
    (驱动 shipped StepTreeAccumulatorDeriver)。"""
    SpineContext.set_run("r_tc")
    run_dir = tmp_path / "r_tc"
    deriver = StepTreeAccumulatorDeriver(
        run_id="r_tc",
        run_dir=run_dir,
        agent_role="agt_test",
        strategy_key="solo",
        plan_ref="plan_test",
    )

    deriver.on_event(_make_event(sequence=1, run_id="r_tc", payload={"phase": "act", "step_id": "step_001"}))
    deriver.on_event(
        _make_event(
            execution_point="step.tool_call.record",
            sequence=2,
            run_id="r_tc",
            channel="fact",
            payload={
                "tool_name": "executeCode",
                "args_digest": "sha256:abc",
                "args_payload_path": None,
                "call_seq": 7,
                "invocation_id": "inv-001",
                "arguments": {"code": "print('hi')"},
                "arguments_summary": "code=\"print('hi')\"",
                "incarnation": 1,
                "plan_ref": "plan_test",
                "step_index": 1,
            },
        )
    )
    deriver.on_event(
        _make_event(
            execution_point="step.tool_result.record",
            sequence=3,
            run_id="r_tc",
            channel="fact",
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
        )
    )
    deriver.on_event(
        _make_event(
            execution_point="writable.step.end",
            sequence=4,
            run_id="r_tc",
            channel="control",
            payload={"step_id": "step_001"},
            outcome="success",
        )
    )

    deriver.flush()

    doc = read_step_document(run_dir / "journal.json")
    assert len(doc.steps) == 1, f"expected 1 step, got {len(doc.steps)}"
    step = doc.steps[0]
    assert step.tool_call is not None, "tool_call missing"
    assert step.tool_call.name == "executeCode"
    assert step.tool_call.invocation_id == "inv-001"
    assert step.tool_call.arguments == {"code": "print('hi')"}
    assert step.tool_call.arguments_summary == "code=\"print('hi')\""

    assert step.tool_result is not None, "tool_result missing"
    assert step.tool_result.ok is True
    assert step.tool_result.latency_ms == 240
    assert step.tool_result.stdout_head == "hi\n"
    assert step.tool_result.files_created == ("out.txt",)
    assert step.tool_result.delta_summary == "✅ stdout[:80] = hi"


def test_step_tree_records_tool_call_nested_fallback(tmp_path: Path) -> None:
    """历史 ``payload.call.*`` nested 形态(``writable_matrix.coordinator``
    路径)依然被支持 — 但 canonical flat 优先,nested 仅在 canonical
    字段缺失时兜底。"""
    SpineContext.set_run("r_nest")
    run_dir = tmp_path / "r_nest"
    deriver = StepTreeAccumulatorDeriver(
        run_id="r_nest",
        run_dir=run_dir,
        agent_role="agt",
        strategy_key="solo",
        plan_ref="plan",
    )

    deriver.on_event(_make_event(sequence=1, run_id="r_nest", payload={"phase": "act", "step_id": "step_001"}))
    deriver.on_event(
        _make_event(
            execution_point="step.tool_call.record",
            sequence=2,
            run_id="r_nest",
            channel="fact",
            payload={
                "call": {
                    "invocation_id": "inv-nested",
                    "name": "legacy_tool",
                    "arguments": {"x": 1},
                    "arguments_summary": "x=1",
                },
                "tool_name": "modern_tool",  # canonical 优先
            },
        )
    )
    deriver.on_event(
        _make_event(
            execution_point="writable.step.end",
            sequence=3,
            run_id="r_nest",
            outcome="success",
            payload={"step_id": "step_001"},
        )
    )

    deriver.flush()
    doc = read_step_document(run_dir / "journal.json")
    assert len(doc.steps) == 1, f"expected 1 step, got {len(doc.steps)}"
    step = doc.steps[0]
    assert step.tool_call is not None
    # canonical flat 命中 tool_name;invocation_id 由 nested 提供。
    assert step.tool_call.name == "modern_tool"
    assert step.tool_call.invocation_id == "inv-nested"
    # arguments / arguments_summary 从 nested 取(flat 没给)。
    assert step.tool_call.arguments == {"x": 1}
    assert step.tool_call.arguments_summary == "x=1"


# ── 3. RunOutcomeProjector.failed auto-emits exception.caught ───────────


class _CapturingJournal:
    def __init__(self) -> None:
        self.facts: list[object] = []

    def commit_fact(self, fact, *, plan_ref, node_ref):  # type: ignore[no-untyped-def]
        self.facts.append(fact)
        return fact.fact_id or f"{node_ref}:fact:{len(self.facts)}"

    def commit_evidence(self, evidence_ref, *, plan_ref, node_ref):  # type: ignore[no-untyped-def]
        return evidence_ref

    def commit_observation(self, observation, *, plan_ref, node_ref):  # type: ignore[no-untyped-def]
        return f"{node_ref}:observation:1"


def test_outcome_projector_failed_emits_exception_caught(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``RunOutcomeProjector.failed`` 必须先把异常归一化落
    ``exception.caught`` spine event,再 ``commit_fact`` —— 这是
    run_3e48052e6c36 失败时 ``exceptions.jsonl`` 为空的根因修复。

    通过 stub ``emit_exception_caught`` 验证被调用 + payload 携带
    ``traceback_text``。
    """
    from lca.harness.declarative.graph.traversal import PhaseTraversal

    journal = _CapturingJournal()
    captured: list[dict] = []

    def _fake_safe_append(*, execution_point, channel, payload=None, outcome=None):  # type: ignore[no-untyped-def]
        # payload 是 record.asdict() 展开后的 dict
        captured.append(payload)
        return None

    monkeypatch.setattr(
        "lca.infrastructure.observability.spine.exception_emit._safe_append",
        _fake_safe_append,
    )

    projector = RunOutcomeProjector(
        journal,  # type: ignore[arg-type]
        run_id="run_test",
        trace_id="trace_test",
        boundary="declarative.interpreter._drive",
    )
    traversal = PhaseTraversal.start(
        plan_ref="plan_x",
        entry_node_id="node_x",
        artifacts={},
        input=None,
    )
    state = AgentState(
        trace_id="trace_test",
        task="t",
        budget=Budget(),
        extra={"run_id": "run_test"},
    )

    err = RuntimeError("PG-007: node visit budget exhausted: perceive.main")
    projector.failed(
        err,
        traversal=traversal,
        state=state,
        plan_ref="plan_x",
        visits=[],
        facts=[],
        reason="validation_error",
        error_code="PG-007",
    )

    # 必须归一化并落 exception.caught。
    assert captured, "exception.caught was not emitted"
    payload = captured[0]
    assert payload["exception_class"].endswith("RuntimeError")
    assert "PG-007" in payload["exception_message"]
    assert payload["traceback_text"], "traceback_text must be populated"
    assert payload["run_id"] == "run_test"
    assert payload["trace_id"] == "trace_test"
    assert payload["boundary"].startswith("declarative.interpreter._drive")

    # RunFact 也必须带 traceback 字符串,作为 sidecar 失败的次级兜底。
    run_failed = next(f for f in journal.facts if getattr(f, "kind", "") == "run.failed")
    assert run_failed.payload["traceback"], "traceback must be on RunFact"
    assert "PG-007" in run_failed.payload["traceback"]


# ── 4. H-seg 一致性:act.fold 在 step close 之后到达也 attach ────────────


def test_phase_act_fold_after_step_close_attaches_to_closed_step(
    tmp_path: Path,
) -> None:
    """``brain.think.end`` 之后 cursor 还在 act 窗口发 ``phase.act.fold``,
    deriver 必须把它 attach 到刚 close 的 step (而不是 orphan 到 _phases),
    让 H-seg 报 ``sum(steps.segments) == totals.segments`` —— 否则
    doctor 永远抓不到这一类物化漏算。

    这是 run_6f2b73a32d32 那种"totals.segments=8 但 sum(steps.segments)=6"
    的直接根因 (verifiable on the shipped StepTreeAccumulatorDeriver)。
    """
    SpineContext.set_run("r_hseg")
    run_dir = tmp_path / "r_hseg"
    deriver = StepTreeAccumulatorDeriver(
        run_id="r_hseg",
        run_dir=run_dir,
        agent_role="agt",
        strategy_key="solo",
        plan_ref="plan",
    )

    # step_001: brain.think.start → 3 think.fold → brain.think.end
    # 然后 phase.act.fold 在 think.end 之后到达(orphan 路径)
    deriver.on_event(_make_event(
        run_id="r_hseg",
        execution_point="brain.think.start",
        sequence=1,
        payload={"state_id": "x"},
    ))
    for i, seq in enumerate((2, 3, 4), start=1):
        deriver.on_event(_make_event(
            run_id="r_hseg",
            execution_point="phase.think.fold",
            sequence=seq,
            payload={"phase": "think", "summary": "t1"},
        ))
    deriver.on_event(_make_event(
        run_id="r_hseg",
        execution_point="brain.think.end",
        sequence=5,
        outcome="success",
        payload={"state_id": "x"},
    ))
    # 这里 _open_step 已被 close step_001,_closed_frames[-1] = step_001
    deriver.on_event(_make_event(
        run_id="r_hseg",
        execution_point="phase.act.fold",
        sequence=6,
        payload={"phase": "act", "summary": "orphan-act"},
    ))

    deriver.flush()

    doc = read_step_document(run_dir / "journal.json")
    assert len(doc.steps) == 1, f"expected 1 step, got {len(doc.steps)}"
    step = doc.steps[0]
    # 3 think.fold + 1 act.fold 都必须 attach 到 step_001
    seg_kinds = [seg.kind for seg in step.segments]
    assert seg_kinds.count("think") == 3, f"expected 3 think segs, got {seg_kinds.count('think')}"
    assert seg_kinds.count("act") == 1, f"act.fold must attach to closed step_001, got segs={seg_kinds}"

    # H-seg 校验:sum(steps.segments) == totals.segments(都是 4)
    sum_segs = sum(len(s.segments) for s in doc.steps)
    assert sum_segs == doc.totals.segments, (
        f"H-seg 不一致:sum(steps.segments)={sum_segs} != totals.segments={doc.totals.segments}"
    )
