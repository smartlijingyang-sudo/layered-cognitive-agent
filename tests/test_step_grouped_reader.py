"""StepGroupedReader 单测(ADR-0164 草案 Phase 2)。

覆盖:
- round-trip: write → read → dataclass 等价
- FileNotFoundError 友好
- schema 校验 (lca.journal/3)
- 嵌套 dataclass 正确还原 (thinking.tool_call.arguments 等)
- tuples 还原为 tuple
- StepGroupedReader 类存在性 + read/exists
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.contracts.models.observability import (
    JournalDocument,
    JournalMetadata,
    JournalStep,
    append_step,
    close_document,
    empty_document,
)
from lca.infrastructure.observability.journal.step import (
    StepGroupedProjector,
    StepGroupedReader,
    read_step_document,
)


def _build_sample_doc() -> JournalDocument:
    from lca.contracts.models.observability import (
        AttachmentRef,
        ReflectTrace,
        SpanRecord,
        StepContext,
        ThinkingTrace,
        ToolCallRecord,
        ToolResult,
    )

    meta = JournalMetadata(
        agent_role="agt_test",
        strategy_key="solo",
        plan_ref="plan_001",
        objective="test",
        attachments=(
            AttachmentRef(
                attachment_id="a1",
                name="x.xlsx",
                mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                size_bytes=100,
            ),
        ),
    )
    doc = empty_document(run_id="r1", trace_id="t1", metadata=meta, started_at=1000.0)
    step = JournalStep(
        step_id="step_1",
        step_index=1,
        phase="act",
        entered_at=1000.0,
        exited_at=1001.5,
        duration_ms=1500,
        context_before=StepContext(
            objective="test",
            attachments=(
                AttachmentRef(
                    attachment_id="a1",
                    name="x.xlsx",
                    mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    size_bytes=100,
                ),
            ),
            prior_summary_chain=("step 0 ok",),
        ),
        thinking=ThinkingTrace(
            model="qwen3.7-plus",
            latency_ms=100,
            reasoning="decide",
            decision="use_tool",
            tool_call=ToolCallRecord(
                invocation_id="t1",
                name="executeCode",
                arguments={"code": "print(1)", "language": "python"},
                arguments_summary="执行 print(1)",
            ),
        ),
        tool_call=ToolCallRecord(
            invocation_id="t1",
            name="executeCode",
            arguments={"code": "print(1)", "language": "python"},
        ),
        tool_result=ToolResult(
            ok=True,
            latency_ms=50,
            stdout_head="1",
            stdout_chars_total=1,
            files_created=("/var/out/a.pdf",),
            delta_summary="成功",
        ),
        reflect=ReflectTrace(summary="ok", verdict="ok"),
        spans=(SpanRecord(kind="hook_triggered", started_at=1000.5, summary={"a": 1}),),
        outcome="ok",
    )
    doc = append_step(doc, step)
    return close_document(doc, outcome="completed", closed_at=2000.0)


# ── round-trip ──


def test_write_read_round_trip(tmp_path: Path) -> None:
    output = tmp_path / "journal.json"
    original = _build_sample_doc()
    StepGroupedProjector(output).write(original)
    restored = read_step_document(output)
    assert restored.schema == original.schema
    assert restored.run_id == original.run_id
    assert restored.trace_id == original.trace_id
    assert restored.started_at == original.started_at
    assert restored.closed_at == original.closed_at
    assert len(restored.steps) == 1
    s = restored.steps[0]
    assert s.step_id == "step_1"
    assert s.phase == "act"
    assert s.outcome == "ok"
    assert s.duration_ms == 1500
    # 嵌套
    assert s.thinking is not None
    assert s.thinking.model == "qwen3.7-plus"
    assert s.thinking.tool_call is not None
    assert s.thinking.tool_call.arguments["code"] == "print(1)"
    # tuple 还原
    assert isinstance(s.tool_result.files_created, tuple)
    assert s.tool_result.files_created == ("/var/out/a.pdf",)
    assert isinstance(s.spans, tuple)
    assert len(s.spans) == 1
    assert s.spans[0].kind == "hook_triggered"


def test_round_trip_with_multiple_steps(tmp_path: Path) -> None:
    from lca.contracts.models.observability import JournalStep, StepContext

    output = tmp_path / "journal.json"
    meta = JournalMetadata(
        agent_role="agt_test",
        strategy_key="solo",
        plan_ref="plan_001",
        objective="test",
    )
    doc = empty_document(run_id="r1", trace_id="t1", metadata=meta, started_at=0.0)
    for i in range(1, 6):
        s = JournalStep(
            step_id=f"step_{i}",
            step_index=i,
            phase="think",
            entered_at=float(i),
            exited_at=float(i) + 0.5,
            duration_ms=500,
            context_before=StepContext(objective="test"),
            outcome="ok",
        )
        doc = append_step(doc, s)
    doc = close_document(doc, outcome="completed", closed_at=10.0)
    StepGroupedProjector(output).write(doc)

    restored = read_step_document(output)
    assert len(restored.steps) == 5
    assert [s.step_index for s in restored.steps] == [1, 2, 3, 4, 5]


# ── 边界 ── ──


def test_read_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="journal step file not found"):
        read_step_document(tmp_path / "nope.json")


def test_read_wrong_schema_raises(tmp_path: Path) -> None:
    output = tmp_path / "journal.json"
    output.write_text(json.dumps({"schema": "lca.journal/2", "steps": []}), encoding="utf-8")
    with pytest.raises(ValueError, match=r"lca.journal/3"):
        read_step_document(output)


def test_step_grouped_reader_class(tmp_path: Path) -> None:
    output = tmp_path / "journal.json"
    reader = StepGroupedReader(output)
    assert not reader.exists()
    StepGroupedProjector(output).write(_build_sample_doc())
    assert reader.exists()
    doc = reader.read()
    assert doc.schema == "lca.journal/3"
    assert doc.run_id == "r1"


def test_read_chinese_unicode_preserved(tmp_path: Path) -> None:
    output = tmp_path / "journal.json"
    meta = JournalMetadata(
        agent_role="agt_test",
        strategy_key="solo",
        plan_ref="plan_001",
        objective="分析生成pdf版本",
    )
    doc = empty_document(run_id="r1", trace_id="t1", metadata=meta, started_at=0.0)
    doc = close_document(doc, outcome="completed", closed_at=1.0)
    StepGroupedProjector(output).write(doc)
    restored = read_step_document(output)
    assert restored.metadata.objective == "分析生成pdf版本"


def test_read_minimal_document(tmp_path: Path) -> None:
    """0 step + 0 attachment 的最小 document 能 round-trip。"""
    output = tmp_path / "journal.json"
    meta = JournalMetadata(
        agent_role="",
        strategy_key="",
        plan_ref="",
        objective="",
    )
    doc = empty_document(run_id="r", trace_id="t", metadata=meta, started_at=0.0)
    doc = close_document(doc, outcome="failed", closed_at=1.0)
    StepGroupedProjector(output).write(doc)
    restored = read_step_document(output)
    assert restored.steps == ()
    assert restored.metadata.outcome == "failed"
