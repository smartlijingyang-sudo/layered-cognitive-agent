"""Doctor v3 单测(ADR-0164 草案 Phase 4)。

覆盖:
- step-tree 主路径 diagnose_step_tree
- 模式 backend / ui 切换
- H8 步骤因果链完整性(成功 / 失败)
- schema="doctor.v3" + 增 mode 字段
- 文件不存在 / 文件损坏 友好错误
- legacy.jsonl 走 legacy 路径
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.models.observability import (
    JournalMetadata,
    JournalStep,
    ReflectTrace,
    StepContext,
    append_step,
    close_document,
    empty_document,
)
from lca.infrastructure.observability.journal.step.projector import JournalDocumentWriter
from lca.plugins.transport.webserver.handlers.runs.doctor.doctor import (
    diagnose,
    diagnose_step_tree,
)


def _build_doc(*, broken_chain: bool = False, fail_step: int | None = None) -> object:
    """构造一个 step 序列 document。"""
    from lca.contracts.models.observability.journal_step import (
        ToolCallRecord,
        ToolResult,
        summarize_step,
    )

    meta = JournalMetadata(
        agent_role="x",
        strategy_key="solo",
        plan_ref="",
        objective="test",
    )
    doc = empty_document(run_id="r1", trace_id="t1", metadata=meta, started_at=0.0)
    prev_summary: str | None = None
    for i in range(1, 5):
        outcome = "fail" if i == fail_step else "ok"
        chain: tuple[str, ...] = ()
        if prev_summary is not None:
            chain = ("WRONG",) if broken_chain else (prev_summary,)
        s = JournalStep(
            step_id=f"step_{i}",
            step_index=i,
            phase="act",
            entered_at=0.0,
            exited_at=1.0,
            duration_ms=1000,
            context_before=StepContext(
                objective="test",
                prior_summary_chain=chain,
            ),
            tool_call=ToolCallRecord(invocation_id=f"t{i}", name="exec", arguments={"k": str(i)}),
            tool_result=ToolResult(
                ok=outcome == "ok",
                latency_ms=100,
                delta_summary=f"step {i}",
                error="boom" if outcome == "fail" else None,
            ),
            reflect=ReflectTrace(
                summary=f"step {i} done" if outcome == "ok" else f"step {i} failed"
            ),
            outcome=outcome,
            error="boom" if outcome == "fail" else None,
        )
        doc = append_step(doc, s)
        # step i 的下一轮期望摘要 = summarize_step(s)
        prev_summary = summarize_step(s)
    return close_document(
        doc, outcome="completed" if fail_step is None else "failed", closed_at=10.0
    )


def _write_doc(tmp_path: Path, doc, name: str = "journal.json") -> Path:
    p = tmp_path / name
    JournalDocumentWriter(p).write(doc)
    return p


# ── 基础 ──


def test_diagnose_step_tree_returns_v3(tmp_path: Path) -> None:
    doc = _build_doc()
    path = _write_doc(tmp_path, doc)
    report = diagnose_step_tree(path)
    assert report.schema == "doctor.v3"
    assert report.mode == "backend"
    assert "H1" in report.hops
    assert "H8" in report.hops


def test_default_mode_is_backend() -> None:
    report = diagnose_step_tree("/nonexistent")
    assert report.mode == "backend"


def test_explicit_ui_mode(tmp_path: Path) -> None:
    doc = _build_doc()
    path = _write_doc(tmp_path, doc)
    report = diagnose_step_tree(path, mode="ui")
    assert report.mode == "ui"


# ── H1 / H2 / H3 / H6 ──


def test_h1_missing_file_is_fail() -> None:
    report = diagnose_step_tree("/nonexistent/journal.json")
    h1 = report.hops["H1"]
    assert h1.ok is False
    assert "不存在" in h1.detail


def test_h1_present_file_is_ok(tmp_path: Path) -> None:
    doc = _build_doc()
    path = _write_doc(tmp_path, doc)
    report = diagnose_step_tree(path)
    h1 = report.hops["H1"]
    assert h1.ok is True


def test_h2_closed_doc_ok(tmp_path: Path) -> None:
    doc = _build_doc()
    path = _write_doc(tmp_path, doc)
    report = diagnose_step_tree(path)
    h2 = report.hops["H2"]
    assert h2.ok is True
    assert h2.extra["total_steps"] == 4


def test_h3_steps_sequential_ok(tmp_path: Path) -> None:
    doc = _build_doc()
    path = _write_doc(tmp_path, doc)
    report = diagnose_step_tree(path)
    h3 = report.hops["H3"]
    assert h3.ok is True


def test_h6_outcome_completed_with_objective_ok(tmp_path: Path) -> None:
    doc = _build_doc()
    path = _write_doc(tmp_path, doc)
    report = diagnose_step_tree(path, mode="backend")
    h6 = report.hops["H6"]
    assert h6.ok is True
    assert h6.extra["outcome"] == "completed"


def test_h6_outcome_failed_is_fail(tmp_path: Path) -> None:
    doc = _build_doc(fail_step=2)
    path = _write_doc(tmp_path, doc)
    report = diagnose_step_tree(path)
    h6 = report.hops["H6"]
    assert h6.ok is False
    assert "未完成" in h6.detail or "failed" in h6.extra["outcome"]


# ── H4 / H5 mode 区分 ──


def test_h4_backend_mode_skipped(tmp_path: Path) -> None:
    doc = _build_doc()
    path = _write_doc(tmp_path, doc)
    report = diagnose_step_tree(path, mode="backend")
    h4 = report.hops["H4"]
    assert h4.ok is None
    assert "mode=backend" in h4.detail


def test_h5_backend_mode_skipped(tmp_path: Path) -> None:
    doc = _build_doc()
    path = _write_doc(tmp_path, doc)
    report = diagnose_step_tree(path, mode="backend")
    h5 = report.hops["H5"]
    assert h5.ok is None
    assert "mode=backend" in h5.detail


def test_h4_ui_mode_explicit_skipped(tmp_path: Path) -> None:
    """ui mode 但 server 看不到 browser, 仍 ok=None(frontend health 跑不动)。"""
    doc = _build_doc()
    path = _write_doc(tmp_path, doc)
    report = diagnose_step_tree(path, mode="ui")
    h4 = report.hops["H4"]
    assert h4.ok is None
    # 但 detail 不再说 "mode=backend"
    assert "mode=backend" not in h4.detail


# ── H7 工具成功率 ──


def test_h7_no_tools_none(tmp_path: Path) -> None:
    """无 tool_call 的 step → H7 ok=None(no tools calls.。"""
    # 不传 tool_call —— _build_doc_with_no_tools
    from lca.contracts.models.observability.journal_step import ReflectTrace

    meta = JournalMetadata(agent_role="x", strategy_key="solo", plan_ref="", objective="t")
    doc = empty_document(run_id="r", trace_id="t", metadata=meta, started_at=0.0)
    s = JournalStep(
        step_id="s1",
        step_index=1,
        phase="perceive",
        entered_at=0.0,
        outcome="ok",
        reflect=ReflectTrace(summary="感知"),
        # 没 tool_call
    )
    doc = append_step(doc, s)
    doc = close_document(doc, outcome="completed", closed_at=1.0)
    path = _write_doc(tmp_path, doc)
    report = diagnose_step_tree(path)
    h7 = report.hops["H7"]
    assert h7.ok is None
    assert "no tool calls" in h7.detail


# ── H8 步骤因果链完整性(新) ──


def test_h8_intact_chain_ok(tmp_path: Path) -> None:
    doc = _build_doc(broken_chain=False)
    path = _write_doc(tmp_path, doc)
    report = diagnose_step_tree(path)
    h8 = report.hops["H8"]
    assert h8.ok is True
    assert "全部 4 步因果链闭合" in h8.detail


def test_h8_broken_chain_is_fail(tmp_path: Path) -> None:
    doc = _build_doc(broken_chain=True)
    path = _write_doc(tmp_path, doc)
    report = diagnose_step_tree(path)
    h8 = report.hops["H8"]
    assert h8.ok is False
    assert "因果链断裂" in h8.detail
    assert 2 in h8.extra["failed_chain_steps"]


def test_h8_single_step_skipped(tmp_path: Path) -> None:
    """< 2 step → H8 ok=None(< 2 steps 无因果链。"""
    meta = JournalMetadata(agent_role="x", strategy_key="solo", plan_ref="", objective="t")
    doc = empty_document(run_id="r", trace_id="t", metadata=meta, started_at=0.0)
    s = JournalStep(
        step_id="s1",
        step_index=1,
        phase="think",
        entered_at=0.0,
        outcome="ok",
    )
    doc = append_step(doc, s)
    doc = close_document(doc, outcome="completed", closed_at=1.0)
    path = _write_doc(tmp_path, doc)
    report = diagnose_step_tree(path)
    h8 = report.hops["H8"]
    assert h8.ok is None
    assert "< 2 steps" in h8.detail


# ── broken_hop / summary ──


def test_broken_hop_identifies_h8_failure(tmp_path: Path) -> None:
    doc = _build_doc(broken_chain=True)
    path = _write_doc(tmp_path, doc)
    report = diagnose_step_tree(path)
    assert report.broken_hop == "H8"


def test_summary_contains_total_steps(tmp_path: Path) -> None:
    doc = _build_doc()
    path = _write_doc(tmp_path, doc)
    report = diagnose_step_tree(path)
    assert "4 steps" in report.summary


# ── as_dict 序列化 ──


def test_as_dict_includes_v3_fields(tmp_path: Path) -> None:
    doc = _build_doc()
    path = _write_doc(tmp_path, doc)
    report = diagnose_step_tree(path)
    payload = report.as_dict()
    assert payload["schema"] == "doctor.v3"
    assert payload["mode"] == "backend"
    assert "H8" in payload["hops"]
    assert payload["journal_path"] == str(path)


# ── doctor.py 路由 ──


def test_diagnose_routes_step_tree(tmp_path: Path) -> None:
    doc = _build_doc()
    path = _write_doc(tmp_path, doc, name="journal.json")
    report = diagnose(None, path, mode="backend")
    assert report.schema == "doctor.v3"
    assert report.mode == "backend"


def test_diagnose_routes_legacy_jsonl(tmp_path: Path) -> None:
    """legacy .jsonl 走 diagnose_legacy(v2 子集,但 schema=v3)。"""
    path = tmp_path / "journal.jsonl"
    path.write_text("", encoding="utf-8")
    report = diagnose(None, path, mode="backend")
    # schema 升级到 v3, 但 hops 是 legacy 集合(无 H8)
    assert report.schema == "doctor.v3"
    assert "H8" not in report.hops  # legacy 路径不产生 H8
