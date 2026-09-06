"""StepNarrativeWriter 单测(ADR-0164 草案 Phase 4)。

覆盖:
- 完整 JournalDocument → narrative.md 落盘
- summary 表格正确(step + phase + duration + outcome + 摘要)
- 每个 step 有 context / thinking / tool_call / tool_result / reflect 子节
- spans 折叠在 <details>
- 中文原样保留
- 失败 step 在 summary 表里有 ✗
- 空 document(0 step) 也能渲染
- 文件不存在 → 错误友好
- 写得不能再开 details 就隐藏在 markdown
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.models.observability import (
    AttachmentRef,
    JournalDocument,
    JournalMetadata,
    JournalStep,
    ReflectTrace,
    SpanRecord,
    StepContext,
    ThinkingTrace,
    ToolCallRecord,
    ToolResult,
    append_step,
    close_document,
    empty_document,
)
from lca.infrastructure.observability.journal.step.narrative_writer import (
    StepNarrativeWriter,
)


def _build_sample_doc() -> JournalDocument:
    """构造上次 PDF run 的 9 步样本。"""
    meta = JournalMetadata(
        agent_role="agt_x",
        strategy_key="solo",
        plan_ref="plan_001",
        objective="分析生成pdf版本",
        attachments=(
            AttachmentRef(
                attachment_id="att_xlsx",
                name="2025年度工作计划表-李超_金融科技.xlsx",
                mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                size_bytes=176071,
            ),
        ),
    )
    doc = empty_document(run_id="r_demo", trace_id="t_demo", metadata=meta, started_at=1000.0)
    # step 1: perceive
    s1 = JournalStep(
        step_id="step_1",
        step_index=1,
        phase="perceive",
        entered_at=1000.0,
        exited_at=1000.5,
        duration_ms=500,
        context_before=StepContext(
            objective="分析生成pdf版本",
            attachments=(
                AttachmentRef(
                    attachment_id="att_xlsx",
                    name="2025年度工作计划表-李超_金融科技.xlsx",
                    mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    size_bytes=176071,
                ),
            ),
        ),
        reflect=ReflectTrace(summary="读取1 sheet 15×256 列"),
        outcome="ok",
    )
    # step 2: think
    s2 = JournalStep(
        step_id="step_2",
        step_index=2,
        phase="think",
        entered_at=1000.5,
        exited_at=1001.0,
        duration_ms=500,
        context_before=StepContext(
            objective="分析生成pdf版本",
            prior_summary_chain=("ok (perceive): 读取1 sheet 15×256 列",),
        ),
        thinking=ThinkingTrace(
            model="qwen3.7-plus",
            latency_ms=7203,
            reasoning="Let me check the Excel structure",
            decision="use_tool",
        ),
        reflect=ReflectTrace(summary="决定 openpyxl 读表"),
        outcome="ok",
    )
    # step 3: act (FAIL)
    s3 = JournalStep(
        step_id="step_3",
        step_index=3,
        phase="act",
        entered_at=1001.0,
        exited_at=1023.0,
        duration_ms=22000,
        context_before=StepContext(
            objective="分析生成pdf版本",
            prior_summary_chain=("ok (think): 决定 openpyxl 读表",),
        ),
        tool_call=ToolCallRecord(
            invocation_id="t1",
            name="executeCode",
            arguments={"code": "doc.build(story)"},
            arguments_summary="渲染 PDF",
        ),
        tool_result=ToolResult(
            ok=False,
            latency_ms=2138,
            error="LayoutError: <Table 5x22, row 509.5pt> too large on page 2 in frame 'normal'",
            stderr="reportlab.platypus.doctemplate.LayoutError",
            delta_summary="❌ LayoutError 列数 × 行高 超 A4 框",
        ),
        reflect=ReflectTrace(summary="❌ LayoutError"),
        outcome="fail",
        error="LayoutError",
    )
    # step 4: act (SUCCESS)
    s4 = JournalStep(
        step_id="step_4",
        step_index=4,
        phase="act",
        entered_at=1023.0,
        exited_at=1034.0,
        duration_ms=11000,
        context_before=StepContext(
            objective="分析生成pdf版本",
            prior_summary_chain=("fail @ act: LayoutError",),
        ),
        tool_call=ToolCallRecord(
            invocation_id="t2",
            name="executeCode",
            arguments={"code": "doc.build(story)"},
            arguments_summary="重试渲染",
        ),
        tool_result=ToolResult(
            ok=True,
            latency_ms=5000,
            files_created=("/var/out/2026年度工作计划-李超_金融科技.pdf",),
            delta_summary="✅ PDF 11.3 KB 写入",
        ),
        reflect=ReflectTrace(summary="✅ PDF 已生成"),
        outcome="ok",
        spans=(
            SpanRecord(kind="hook_triggered", started_at=1023.5, summary={"attempt": 1}),
            SpanRecord(kind="tool_retry_progress", started_at=1024.0, summary={"retry": 1}),
        ),
    )
    for step in (s1, s2, s3, s4):
        doc = append_step(doc, step)
    return close_document(doc, outcome="completed", closed_at=1035.0)


# ── 基础 ──


def test_write_creates_file(tmp_path: Path) -> None:
    output = tmp_path / "narrative.md"
    writer = StepNarrativeWriter(output)
    written = writer.write(_build_sample_doc())
    assert written == output
    assert output.exists()


def test_output_starts_with_objective(tmp_path: Path) -> None:
    writer = StepNarrativeWriter(tmp_path / "narrative.md")
    text = writer.render(_build_sample_doc())
    assert text.startswith("# Run Narrative —— 分析生成pdf版本")


def test_header_contains_run_id_trace_id(tmp_path: Path) -> None:
    writer = StepNarrativeWriter(tmp_path / "narrative.md")
    text = writer.render(_build_sample_doc())
    assert "run_id=`r_demo`" in text
    assert "trace_id=`t_demo`" in text


# ── Summary 表 ──


def test_summary_table_contains_all_steps(tmp_path: Path) -> None:
    writer = StepNarrativeWriter(tmp_path / "narrative.md")
    text = writer.render(_build_sample_doc())
    # 表格行
    assert "| 1 |" in text
    assert "| 2 |" in text
    assert "| 3 |" in text
    assert "| 4 |" in text
    # 表头
    assert "| # | phase | duration | outcome | 摘要 |" in text


def test_summary_table_marks_failed_with_x(tmp_path: Path) -> None:
    writer = StepNarrativeWriter(tmp_path / "narrative.md")
    text = writer.render(_build_sample_doc())
    # step 3 fail
    assert "✗" in text
    assert "| 3 | act | 22.0s | ✗ fail" in text


def test_summary_table_marks_success_with_check(tmp_path: Path) -> None:
    writer = StepNarrativeWriter(tmp_path / "narrative.md")
    text = writer.render(_build_sample_doc())
    assert "✓" in text
    # step 1, 2, 4 ok
    assert "| 1 | perceive | 500ms | ✓ ok" in text


def test_summary_table_shows_objective_and_outcome(tmp_path: Path) -> None:
    writer = StepNarrativeWriter(tmp_path / "narrative.md")
    text = writer.render(_build_sample_doc())
    assert "objective: `分析生成pdf版本`" in text
    assert "outcome: **completed**" in text


# ── Step 详述 ──


def test_each_step_has_phase_section(tmp_path: Path) -> None:
    writer = StepNarrativeWriter(tmp_path / "narrative.md")
    text = writer.render(_build_sample_doc())
    assert "### Step 1: 🔍 perceive" in text
    assert "### Step 2: 🧠 think" in text
    assert "### Step 3: ⚙️ act" in text
    assert "### Step 4: ⚙️ act" in text


def test_context_section_lists_attachments(tmp_path: Path) -> None:
    writer = StepNarrativeWriter(tmp_path / "narrative.md")
    text = writer.render(_build_sample_doc())
    assert "**上下文**:" in text
    assert "2025年度工作计划表-李超_金融科技.xlsx" in text


def test_context_section_shows_prior_summary_chain(tmp_path: Path) -> None:
    writer = StepNarrativeWriter(tmp_path / "narrative.md")
    text = writer.render(_build_sample_doc())
    assert "prior_summary_chain" in text
    assert "fail @ act: LayoutError" in text


def test_thinking_section_shows_model_and_decision(tmp_path: Path) -> None:
    writer = StepNarrativeWriter(tmp_path / "narrative.md")
    text = writer.render(_build_sample_doc())
    assert "**思考**:" in text
    assert "model: `qwen3.7-plus`" in text
    assert "decision: `use_tool`" in text


def test_tool_call_section_shows_invocation(tmp_path: Path) -> None:
    writer = StepNarrativeWriter(tmp_path / "narrative.md")
    text = writer.render(_build_sample_doc())
    assert "**工具调用**:" in text
    assert "invocation_id: `t1`" in text
    assert "arguments_summary: 渲染 PDF" in text


def test_tool_result_section_shows_error_for_fail(tmp_path: Path) -> None:
    writer = StepNarrativeWriter(tmp_path / "narrative.md")
    text = writer.render(_build_sample_doc())
    assert "**工具结果**: ✗ fail" in text
    assert "LayoutError" in text
    assert "delta_summary: ❌ LayoutError" in text


def test_tool_result_section_shows_files_for_success(tmp_path: Path) -> None:
    writer = StepNarrativeWriter(tmp_path / "narrative.md")
    text = writer.render(_build_sample_doc())
    assert "**工具结果**: ✓ ok" in text
    assert "2026年度工作计划-李超_金融科技.pdf" in text
    assert "✅ PDF 11.3 KB 写入" in text


def test_spans_collapsed_in_details(tmp_path: Path) -> None:
    writer = StepNarrativeWriter(tmp_path / "narrative.md")
    text = writer.render(_build_sample_doc())
    # step 4 有 2 spans
    assert "<details>" in text
    assert "诊断 (2 spans)" in text
    assert "<summary>" in text
    assert "hook_triggered" in text


def test_chinese_preserved_throughout(tmp_path: Path) -> None:
    writer = StepNarrativeWriter(tmp_path / "narrative.md")
    text = writer.render(_build_sample_doc())
    assert "分析生成pdf版本" in text
    assert "LayoutError" in text
    assert "✅" in text
    assert "❌" in text


# ── 因果链 ──


def test_causal_chain_section_lists_all_steps(tmp_path: Path) -> None:
    writer = StepNarrativeWriter(tmp_path / "narrative.md")
    text = writer.render(_build_sample_doc())
    assert "## 🔗 因果链" in text
    assert "1." in text
    assert "2." in text
    assert "3." in text
    assert "4." in text


# ── 边界 ──


def test_empty_document_renders(tmp_path: Path) -> None:
    meta = JournalMetadata(agent_role="", strategy_key="", plan_ref="", objective="empty run")
    doc = empty_document(run_id="r", trace_id="t", metadata=meta, started_at=0.0)
    doc = close_document(doc, outcome="failed", closed_at=1.0)
    writer = StepNarrativeWriter(tmp_path / "narrative.md")
    text = writer.render(doc)
    assert "# Run Narrative —— empty run" in text
    assert "total_steps: 0" in text
    assert "objective: `empty run`" in text


def test_minimal_step_no_context(tmp_path: Path) -> None:
    """step 没 context_before 也能渲染(防御)。"""
    meta = JournalMetadata(agent_role="x", strategy_key="solo", plan_ref="", objective="t")
    doc = empty_document(run_id="r", trace_id="t", metadata=meta, started_at=0.0)
    s = JournalStep(
        step_id="s1",
        step_index=1,
        phase="perceive",
        entered_at=0.0,
        outcome="ok",
        # 没 context_before / thinking / tool_call / tool_result / reflect
    )
    doc = append_step(doc, s)
    doc = close_document(doc, outcome="completed", closed_at=1.0)
    writer = StepNarrativeWriter(tmp_path / "narrative.md")
    text = writer.render(doc)
    assert "### Step 1: 🔍 perceive" in text
    assert "**上下文**: _(未填)_" in text


def test_duration_format_variants(tmp_path: Path) -> None:
    """测试不同时长格式。"""
    meta = JournalMetadata(agent_role="x", strategy_key="solo", plan_ref="", objective="t")
    doc = empty_document(run_id="r", trace_id="t", metadata=meta, started_at=0.0)
    # ms / s / m
    for i, dur in enumerate([100, 5500, 120000], 1):
        s = JournalStep(
            step_id=f"s{i}",
            step_index=i,
            phase="think",
            entered_at=0.0,
            exited_at=0.0,
            duration_ms=dur,
            outcome="ok",
        )
        doc = append_step(doc, s)
    doc = close_document(doc, outcome="completed", closed_at=200.0)
    writer = StepNarrativeWriter(tmp_path / "narrative.md")
    text = writer.render(doc)
    assert "100ms" in text
    assert "5.5s" in text
    assert "2.0m" in text


def test_write_appends_metadata_at_end(tmp_path: Path) -> None:
    writer = StepNarrativeWriter(tmp_path / "narrative.md")
    text = writer.render(_build_sample_doc())
    assert "---" in text
    assert "generated by StepNarrativeWriter" in text
    assert "schema=lca.journal/3" in text


# ── Model saw 链接区(ADR-0185 PR-3 spine 优先) ──


def test_model_saw_prefers_spine_when_present(tmp_path: Path) -> None:
    """output_path.parent 即 run_dir;run_dir 下存在 <run_id>.spine.jsonl 时,
    「Model saw」链接走 fold SSOT(与 journal_step.py / journal_replay.py
    PR-3 行为一致)。
    """
    from lca.infrastructure.observability.spine.sinks.naming import (
        spine_filename_for_run,
    )

    run_dir = tmp_path / "run_dir"
    run_dir.mkdir()
    # 文档 run_id="r_demo";spine 文件名按 run_id 派生
    (run_dir / spine_filename_for_run("r_demo")).write_text("{}\n", encoding="utf-8")
    writer = StepNarrativeWriter(run_dir / "journal.narrative.md")
    text = writer.render(_build_sample_doc())
    assert "fold 重建" in text
    assert "lca_kernel.events.fold.foldRequestHeader" in text
    assert "legacy sidecar" not in text
    # 链接指向 run_dir 解析的 spine,而不是 CWD-relative traces/。
    assert str(run_dir / "r_demo.spine.jsonl") in text


def test_model_saw_falls_back_to_model_visible_when_spine_missing(
    tmp_path: Path,
) -> None:
    """run_dir 下不存在 spine 时,链接走 model_visible/(PR-3 双轨期)。"""
    run_dir = tmp_path / "run_xyz"
    run_dir.mkdir()
    writer = StepNarrativeWriter(run_dir / "journal.narrative.md")
    text = writer.render(_build_sample_doc())
    assert "legacy sidecar" in text
    assert "model_visible" in text
    assert "fold 重建" not in text


def test_model_saw_does_not_read_cwd_relative_traces(tmp_path: Path) -> None:
    """回归锁:spine 路径必须从 output_path.parent 派生,绝不读 CWD 下的 traces/。

    旧实现:``Path("traces") / "runs" / <run_id> / <run_id>.spine.jsonl`` 在
    CWD 是 traces 父目录时才会触发 spine 优先;否则所有 run 都被错打到
    fallback(与 PR-3 CLI 行为脱钩)。
    """
    from lca.infrastructure.observability.spine.sinks.naming import (
        spine_filename_for_run,
    )

    # 在 cwd 旁路放一个 decoy spine.jsonl
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    decoy_dir = cwd / "traces" / "runs" / "r_demo"
    decoy_dir.mkdir(parents=True)
    (decoy_dir / spine_filename_for_run("r_demo")).write_text("{}\n", encoding="utf-8")

    real_run_dir = tmp_path / "real_run"
    real_run_dir.mkdir()
    writer = StepNarrativeWriter(real_run_dir / "journal.narrative.md")

    import os

    old_cwd = os.getcwd()
    try:
        os.chdir(cwd)
        text = writer.render(_build_sample_doc())
    finally:
        os.chdir(old_cwd)

    # 必须走 fallback —— decoy 不可触发 spine 优先
    assert "legacy sidecar" in text
    assert "fold 重建" not in text


def test_model_saw_empty_path_renders_fallback(tmp_path: Path) -> None:
    """``StepNarrativeWriter("")`` 只调 render() 打印;无 run_dir,跳过 spine 探测
    直接走 model_visible/,不误命中 CWD 的 spine.jsonl。
    """
    import os

    cwd = tmp_path / "cwd"
    cwd.mkdir()
    # cwd 下造一个 r_demo.spine.jsonl(同名 + cwd-relative)
    (cwd / "r_demo.spine.jsonl").write_text("{}\n", encoding="utf-8")

    old_cwd = os.getcwd()
    try:
        os.chdir(cwd)
        writer = StepNarrativeWriter("")
        text = writer.render(_build_sample_doc())
    finally:
        os.chdir(old_cwd)

    # 无 run_dir ⇒ 直接 fallback
    assert "legacy sidecar" in text
    assert "fold 重建" not in text
