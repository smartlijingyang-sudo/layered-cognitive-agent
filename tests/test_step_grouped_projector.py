"""StepGroupedProjector 单测(ADR-0164 草案 Phase 2)。

覆盖:
- write 完整 document → journal.json 落盘
- schema 校验 (lca.journal/3)
- 原子写 (tmp → replace)
- pretty-print JSON (indent + ensure_ascii=False)
- 嵌套 dataclass 正确展开 (thinking.tool_call.arguments 保留)
- tuples → lists 序列化
- parent dir 自动创建
- 重复 write 覆盖(不堆叠)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.contracts.models.observability import (
    AttachmentRef,
    JournalDocument,
    JournalMetadata,
    JournalStep,
    ReflectTrace,
    StepContext,
    ThinkingTrace,
    ToolCallRecord,
    ToolResult,
    close_document,
    empty_document,
)
from lca.infrastructure.observability.journal.step import StepGroupedProjector


def _meta() -> JournalMetadata:
    return JournalMetadata(
        agent_role="agt_test",
        strategy_key="solo",
        plan_ref="plan_001",
        objective="test",
    )


def _build_step() -> JournalStep:
    return JournalStep(
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
        ),
        thinking=ThinkingTrace(
            model="qwen3.7-plus",
            latency_ms=100,
            reasoning="let me decide",
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
            delta_summary="成功: 输出 1",
        ),
        reflect=ReflectTrace(summary="ok", verdict="ok"),
        outcome="ok",
    )


def _build_document(tmp_path: Path) -> JournalDocument:
    doc = empty_document(
        run_id="r1",
        trace_id="t1",
        metadata=_meta(),
        started_at=1000.0,
    )
    doc = close_document(doc, outcome="completed", closed_at=2000.0)
    # append_step 替换内部状态
    from lca.contracts.models.observability import append_step

    return append_step(doc, _build_step())


# ── 写 + 校验 ──


def test_write_creates_file(tmp_path: Path) -> None:
    output = tmp_path / "journal.json"
    doc = _build_document(tmp_path)
    projector = StepGroupedProjector(output)
    written = projector.write(doc)
    assert written == output
    assert output.exists()


def test_write_atomic_no_partial_on_failure(tmp_path: Path) -> None:
    """写过程中 schema 校验失败 → 不留 tmp 文件。"""
    output = tmp_path / "journal.json"
    # 构造 schema 错的 doc(用 v2 触发 fail)
    from dataclasses import replace as dc_replace

    bad_doc = dc_replace(_build_document(tmp_path), schema="lca.journal/2")  # type: ignore[arg-type]
    projector = StepGroupedProjector(output)
    with pytest.raises(ValueError, match=r"lca.journal/3"):
        projector.write(bad_doc)  # type: ignore[arg-type]
    # journal.json 不应存在, 也不应有残留 .tmp
    assert not output.exists()
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == []


def test_write_pretty_json_with_chinese(tmp_path: Path) -> None:
    output = tmp_path / "journal.json"
    doc = _build_document(tmp_path)
    StepGroupedProjector(output).write(doc)
    text = output.read_text(encoding="utf-8")
    # pretty-print: 缩进 + 换行
    assert "\n" in text
    assert "  " in text  # indent
    # 中文原样保留(ensure_ascii=False)
    obj = json.loads(text)
    assert obj["metadata"]["objective"] == "test"


def test_write_overwrites_previous(tmp_path: Path) -> None:
    output = tmp_path / "journal.json"
    StepGroupedProjector(output).write(_build_document(tmp_path))
    first_size = output.stat().st_size
    # 第二次写同样大小(同 doc) → 文件被覆盖, 不追加
    StepGroupedProjector(output).write(_build_document(tmp_path))
    second_size = output.stat().st_size
    assert first_size == second_size


def test_write_creates_parent_dirs(tmp_path: Path) -> None:
    output = tmp_path / "deep" / "nested" / "dir" / "journal.json"
    StepGroupedProjector(output, ensure_parents=True).write(_build_document(tmp_path))
    assert output.exists()


def test_write_does_not_create_parent_if_disabled(tmp_path: Path) -> None:
    output = tmp_path / "missing" / "journal.json"
    projector = StepGroupedProjector(output, ensure_parents=False)
    with pytest.raises(FileNotFoundError):
        projector.write(_build_document(tmp_path))


# ── 序列化内容 ──


def test_write_preserves_nested_dataclasses(tmp_path: Path) -> None:
    output = tmp_path / "journal.json"
    StepGroupedProjector(output).write(_build_document(tmp_path))
    obj = json.loads(output.read_text(encoding="utf-8"))
    # 顶层
    assert obj["schema"] == "lca.journal/3"
    assert obj["run_id"] == "r1"
    assert obj["trace_id"] == "t1"
    # step 嵌套展开
    step = obj["steps"][0]
    assert step["step_id"] == "step_1"
    assert step["phase"] == "act"
    assert step["outcome"] == "ok"
    # thinking.tool_call.arguments 完整保留
    assert step["thinking"]["tool_call"]["arguments"]["code"] == "print(1)"
    assert step["thinking"]["model"] == "qwen3.7-plus"
    # attachments tuple → list
    assert isinstance(step["context_before"]["attachments"], list)
    assert step["context_before"]["attachments"][0]["name"] == "x.xlsx"
    # tool_result.files_created tuple → list
    assert step["tool_result"]["files_created"] == ["/var/out/a.pdf"]


def test_write_metadata_at_top(tmp_path: Path) -> None:
    output = tmp_path / "journal.json"
    StepGroupedProjector(output).write(_build_document(tmp_path))
    obj = json.loads(output.read_text(encoding="utf-8"))
    assert "metadata" in obj
    assert obj["metadata"]["agent_role"] == "agt_test"
    assert obj["metadata"]["outcome"] == "completed"


def test_write_empty_steps_serializes(tmp_path: Path) -> None:
    """空 document(0 step)合法 —— run 启动后立即 close 的情况。"""
    output = tmp_path / "journal.json"
    doc = empty_document(
        run_id="r1",
        trace_id="t1",
        metadata=_meta(),
        started_at=0.0,
    )
    doc = close_document(doc, outcome="failed", closed_at=1.0)
    StepGroupedProjector(output).write(doc)
    obj = json.loads(output.read_text(encoding="utf-8"))
    assert obj["steps"] == []
    assert obj["metadata"]["total_steps"] == 0
