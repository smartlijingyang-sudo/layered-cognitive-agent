"""H7 多源对账测试(回归锁 run_1f5360d2fa47)。

H7 不再只读 ``journal.step.tool_result.ok``,而是要把 spine
``phase.tool.call.end.ok`` 与 journal 对账 —— 任何一个被前者
记为失败但 journal 写 ok=True 的工具,都会被识别为失真。

另测 fold invariant 残留矛盾样本的识别路径(``tool_ok_error_conflicts``)。
"""

from __future__ import annotations

import json
from pathlib import Path

from lca.contracts.models.observability import (
    JournalMetadata,
    JournalStep,
    ReflectTrace,
    ThinkingTrace,
    ToolCallRecord,
    ToolResult,
    append_step,
    close_document,
    empty_document,
)
from lca.infrastructure.observability.journal.step.projector import JournalDocumentWriter
from lca.plugins.transport.webserver.doctor.doctor import diagnose_step_tree


def _write_doc(tmp_path: Path, doc) -> Path:
    writer = JournalDocumentWriter(tmp_path / "journal.json")
    writer.write(doc)
    return tmp_path / "journal.json"


def _write_spine(tmp_path: Path, run_id: str, events: list[dict]) -> Path:
    """写一份 spine ledger JSONL。

    Spine records need: event_id, category, execution_point, channel,
    payload, ts. ``_scan_xref`` reads via SpineReader; missing required
    fields cause "malformed record" warnings and silent drop.
    """
    spine = tmp_path / f"{run_id}.spine.jsonl"
    with spine.open("w", encoding="utf-8") as f:
        for i, ev in enumerate(events):
            full = {
                "event_id": f"e{i}",
                "category": "spine." + ev["execution_point"],
                "execution_point": ev["execution_point"],
                "channel": "fact",
                "payload": ev.get("payload", {}),
                "ts": str(1.0 + i),
            }
            f.write(json.dumps(full, ensure_ascii=False) + "\n")
    return spine


def _step_with_tool_result(
    step_index: int,
    *,
    tool_ok: bool,
    error: str | None = None,
    outcome: str = "ok",
    step_id: str | None = None,
) -> JournalStep:
    return JournalStep(
        step_id=step_id or f"s{step_index}",
        step_index=step_index,
        phase="act",
        entered_at=float(step_index),
        outcome=outcome,
        tool_call=ToolCallRecord(
            invocation_id=f"inv-{step_index}",
            name="runCommand",
            arguments={"command": "pdftotext x.pdf"},
        ),
        tool_result=ToolResult(
            ok=tool_ok,
            latency_ms=100,
            error=error,
        ),
        thinking=ThinkingTrace(model="m", latency_ms=10),
        reflect=ReflectTrace(summary="reflection"),
    )


# ── 回归锁 run_1f5360d2fa47 ──────────────────────────────────────────────


def test_regression_run_1f5360d2fa47_journal_says_ok_but_spine_says_failure(tmp_path: Path) -> None:
    """journal.tool_result.ok=True + spine.phase.tool.call.end.ok=False → H7.fail。

    这是 run_1f5360d2fa47 的核心矛盾:journal 失真(原 bug 把 ok=True 写入),
    spine 是真值。修复前 H7.ok=True(报 100% 成功率);修复后 H7.ok=False
    + detail 含 "journal↔spine inconsistency"。

    注:journal 这一步 error 字段必须为空,否则会被 ``tool_ok_error_conflicts``
    分支先一步捕获;本测试聚焦"spine/journal 双源对账"路径。
    """
    meta = JournalMetadata(agent_role="x", strategy_key="solo", plan_ref="p", objective="t")
    doc = empty_document(run_id="run_x", trace_id="t", metadata=meta, started_at=0.0)
    # 3 步:journal 一致地写 tool_ok=True,error=None(模拟 journal 失真,spine 反相)
    for i in (1, 2, 3):
        doc = append_step(
            doc,
            _step_with_tool_result(
                i,
                tool_ok=True,
                error=None,
                outcome="ok",
            ),
        )
    doc = close_document(doc, outcome="failed", closed_at=10.0)
    path = _write_doc(tmp_path, doc)

    # spine:phase.tool.call.end.ok=False ×2(对应 step 1 / 2),step 3 = True
    _write_spine(
        tmp_path,
        "run_x",
        [
            {
                "execution_point": "phase.tool.call.end",
                "payload": {"tool_name": "runCommand", "ok": False, "step": 1},
            },
            {
                "execution_point": "phase.tool.call.end",
                "payload": {"tool_name": "runCommand", "ok": False, "step": 2},
            },
            {
                "execution_point": "phase.tool.call.end",
                "payload": {"tool_name": "runCommand", "ok": True, "step": 3},
            },
        ],
    )

    report = diagnose_step_tree(path)
    h7 = report.hops["H7"]
    assert h7.ok is False
    assert "inconsistency" in h7.detail.lower() or "矛盾" in h7.detail
    extra = h7.extra or {}
    assert extra.get("spine_phase_tool_call_end_failure_count") == 2
    assert extra.get("journal_tool_success") == 3
    assert extra.get("journal_tool_total") == 3


def test_h7_passes_when_journal_and_spine_agree(tmp_path: Path) -> None:
    """journal 与 spine 都报成功 → H7.ok=True。"""
    meta = JournalMetadata(agent_role="x", strategy_key="solo", plan_ref="p", objective="t")
    doc = empty_document(run_id="run_x", trace_id="t", metadata=meta, started_at=0.0)
    for i in (1, 2):
        doc = append_step(doc, _step_with_tool_result(i, tool_ok=True, error=None, outcome="ok"))
    doc = close_document(doc, outcome="completed", closed_at=5.0)
    path = _write_doc(tmp_path, doc)
    _write_spine(
        tmp_path,
        "run_x",
        [
            {"execution_point": "phase.tool.call.end", "payload": {"tool_name": "runCommand", "ok": True, "step": 1}},
            {"execution_point": "phase.tool.call.end", "payload": {"tool_name": "runCommand", "ok": True, "step": 2}},
        ],
    )
    report = diagnose_step_tree(path)
    h7 = report.hops["H7"]
    assert h7.ok is True


def test_h7_detects_journal_ok_true_with_error_residue(tmp_path: Path) -> None:
    """fold invariant 在生产路径上抛;但残留 journal 文件可能含历史矛盾样本。
    doctor 必须把 ``tool_result.ok=True && error != ''`` 视为 H7 失败。
    """
    meta = JournalMetadata(agent_role="x", strategy_key="solo", plan_ref="p", objective="t")
    doc = empty_document(run_id="run_x", trace_id="t", metadata=meta, started_at=0.0)
    doc = append_step(
        doc,
        _step_with_tool_result(
            1,
            tool_ok=True,
            error="sh: 1: pdftotext: not found",
            outcome="ok",
        ),
    )
    doc = close_document(doc, outcome="failed", closed_at=5.0)
    path = _write_doc(tmp_path, doc)
    # spine 也报失败 — 一致,但 journal 内部自相矛盾,doctor 必须识别。
    _write_spine(
        tmp_path,
        "run_x",
        [
            {"execution_point": "phase.tool.call.end", "payload": {"tool_name": "runCommand", "ok": False, "step": 1}},
        ],
    )
    report = diagnose_step_tree(path)
    h7 = report.hops["H7"]
    assert h7.ok is False
    assert "矛盾" in h7.detail
    extra = h7.extra or {}
    assert extra.get("tool_ok_error_conflicts") == [1]


def test_h7_low_success_rate_remains_a_failure(tmp_path: Path) -> None:
    """H7 原有 < 50% 失败率逻辑保留。"""
    meta = JournalMetadata(agent_role="x", strategy_key="solo", plan_ref="p", objective="t")
    doc = empty_document(run_id="run_x", trace_id="t", metadata=meta, started_at=0.0)
    for i in (1, 2, 3):
        doc = append_step(
            doc,
            _step_with_tool_result(
                i,
                tool_ok=(i == 3),  # 1 成功 2 失败
                error="boom" if i != 3 else None,
                outcome="ok" if i == 3 else "fail",
            ),
        )
    doc = close_document(doc, outcome="failed", closed_at=5.0)
    path = _write_doc(tmp_path, doc)
    _write_spine(
        tmp_path,
        "run_x",
        [
            {"execution_point": "phase.tool.call.end", "payload": {"tool_name": "runCommand", "ok": (i == 3), "step": i}}
            for i in (1, 2, 3)
        ],
    )
    report = diagnose_step_tree(path)
    h7 = report.hops["H7"]
    assert h7.ok is False
    assert "33%" in h7.detail or "成功率" in h7.detail


def _phantom_step(step_index: int) -> JournalStep:
    """Phantom step: tool_call with empty invocation_id, no tool_result.

    Matches real-world pattern of an early ``writable.step.start`` with
    no subsequent ``tool_call`` (a "thinking but no tool" frame).
    """
    return JournalStep(
        step_id=f"s{step_index}",
        step_index=step_index,
        phase="act",
        entered_at=float(step_index),
        outcome="ok",
        tool_call=ToolCallRecord(
            invocation_id="",
            name="runCommand",
            arguments={"command": "echo thinking"},
        ),
        tool_result=None,
        thinking=ThinkingTrace(model="m", latency_ms=10),
        reflect=ReflectTrace(summary="reflection"),
    )


# ── PR-D: distinct invocation_id semantics ───────────────────────────────


def test_h7_phantom_step_excluded_from_tool_total(tmp_path: Path) -> None:
    """Phantom step (empty invocation_id, no tool_result) excluded from tool_total.

    4 journal steps: 1 phantom + 3 real with distinct invocation_ids.
    Expected: tool_total=3 (distinct non-empty invocations),
    success_rate=1.0, parity check passes when spine matches.
    """
    meta = JournalMetadata(agent_role="x", strategy_key="solo", plan_ref="p", objective="t")
    doc = empty_document(run_id="run_x", trace_id="t", metadata=meta, started_at=0.0)
    # phantom step at index 0
    doc = append_step(doc, _phantom_step(0))
    # 3 real steps with distinct invocation_ids
    for i in (1, 2, 3):
        doc = append_step(
            doc,
            _step_with_tool_result(i, tool_ok=True, error=None, outcome="ok"),
        )
    doc = close_document(doc, outcome="completed", closed_at=10.0)
    path = _write_doc(tmp_path, doc)

    # spine: 3 phase.tool.call.end events (matches distinct invocations)
    _write_spine(
        tmp_path,
        "run_x",
        [
            {
                "execution_point": "phase.tool.call.end",
                "payload": {"tool_name": "runCommand", "ok": True, "step": i},
            }
            for i in (1, 2, 3)
        ],
    )

    report = diagnose_step_tree(path)
    h7 = report.hops["H7"]
    assert h7.ok is True
    extra = h7.extra or {}
    assert extra.get("tool_total") == 3
    assert extra.get("success_rate") == 1.0


def test_h7_journal_spine_tool_total_mismatch(tmp_path: Path) -> None:
    """Journal distinct invocation count differs from spine total → H7.fail.

    Journal has 3 distinct invocations; spine has only 2 phase.tool.call.end
    events. Parity check must catch this and report mismatch.
    """
    meta = JournalMetadata(agent_role="x", strategy_key="solo", plan_ref="p", objective="t")
    doc = empty_document(run_id="run_x", trace_id="t", metadata=meta, started_at=0.0)
    for i in (1, 2, 3):
        doc = append_step(
            doc,
            _step_with_tool_result(i, tool_ok=True, error=None, outcome="ok"),
        )
    doc = close_document(doc, outcome="completed", closed_at=5.0)
    path = _write_doc(tmp_path, doc)

    # spine: only 2 phase.tool.call.end events (mismatch with journal's 3)
    _write_spine(
        tmp_path,
        "run_x",
        [
            {
                "execution_point": "phase.tool.call.end",
                "payload": {"tool_name": "runCommand", "ok": True, "step": 1},
            },
            {
                "execution_point": "phase.tool.call.end",
                "payload": {"tool_name": "runCommand", "ok": True, "step": 2},
            },
        ],
    )

    report = diagnose_step_tree(path)
    h7 = report.hops["H7"]
    assert h7.ok is False
    assert "mismatch" in h7.detail.lower()
    extra = h7.extra or {}
    assert extra.get("journal_tool_total") == 3
    assert extra.get("spine_phase_tool_call_end_total") == 2


# ── PR-B: H3 step-tree integrity ────────────────────────────────────────


def _make_meta() -> JournalMetadata:
    return JournalMetadata(agent_role="x", strategy_key="solo", plan_ref="p", objective="t")


def test_h3_duplicate_step_id(tmp_path: Path) -> None:
    """两个 step 共享同一个 step_id → H3.ok=False,detail 含 'duplicate step_id'。

    回归场景 run_2910e20390f9:5 步 journal 只有 4 个 distinct step_id。
    """
    doc = empty_document(run_id="run_x", trace_id="t", metadata=_make_meta(), started_at=0.0)
    doc = append_step(doc, _step_with_tool_result(1, tool_ok=True, step_id="step-001"))
    doc = append_step(doc, _step_with_tool_result(2, tool_ok=True, step_id="step-002"))
    doc = append_step(doc, _step_with_tool_result(3, tool_ok=True, step_id="step-001"))  # dup
    doc = close_document(doc, outcome="completed", closed_at=5.0)
    path = _write_doc(tmp_path, doc)

    report = diagnose_step_tree(path)
    h3 = report.hops["H3"]
    assert h3.ok is False
    assert "duplicate step_id" in h3.detail.lower() or "duplicate step_id" in h3.detail


def test_h3_non_contiguous_step_index(tmp_path: Path) -> None:
    """step_index 不连续(如 [1, 3])→ H3.ok=False,detail 含 'step_index'。"""
    meta = _make_meta()
    doc = empty_document(run_id="run_x", trace_id="t", metadata=meta, started_at=0.0)
    # 手动构建 step_index=1 和 step_index=3(跳过 2)
    doc = append_step(
        doc,
        _step_with_tool_result(1, tool_ok=True, step_id="step-001"),
    )
    doc = append_step(
        doc,
        _step_with_tool_result(3, tool_ok=True, step_id="step-003"),
    )
    doc = close_document(doc, outcome="completed", closed_at=5.0)
    path = _write_doc(tmp_path, doc)

    report = diagnose_step_tree(path)
    h3 = report.hops["H3"]
    assert h3.ok is False
    assert "step_index" in h3.detail


def test_h3_clean_journal_passes(tmp_path: Path) -> None:
    """distinct step_id + contiguous step_index → H3.ok=True。"""
    doc = empty_document(run_id="run_x", trace_id="t", metadata=_make_meta(), started_at=0.0)
    for i in (1, 2, 3):
        doc = append_step(
            doc,
            _step_with_tool_result(i, tool_ok=True, step_id=f"step-{i:03d}"),
        )
    doc = close_document(doc, outcome="completed", closed_at=5.0)
    path = _write_doc(tmp_path, doc)

    report = diagnose_step_tree(path)
    h3 = report.hops["H3"]
    assert h3.ok is True
