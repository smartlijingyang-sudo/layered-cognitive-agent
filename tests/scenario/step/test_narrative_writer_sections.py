"""narrative_writer.sections 渲染器单测(拆包后直接测子节渲染)。

覆盖:
- _render_tool_call 输出 shape(name / invocation_id / arguments_summary)
- _render_reflect 输出 shape(summary / verdict)
- _render_spans 对 reasoning_delta 类 token span 的 coalesce
"""

from __future__ import annotations

from lca.contracts.models.observability import (
    ReflectTrace,
    SpanRecord,
    ToolCallRecord,
)
from lca.infrastructure.observability.journal.step.narrative_writer.sections import (
    _render_reflect,
    _render_spans,
    _render_tool_call,
)


def test_render_tool_call_output_shape() -> None:
    call = ToolCallRecord(
        invocation_id="inv_1",
        name="executeCode",
        arguments={"code": "doc.build(story)"},
        arguments_summary="渲染 PDF",
    )
    lines = _render_tool_call(call)
    assert lines[0] == "**工具调用**:"
    assert lines[1] == "- name: `executeCode`"
    assert lines[2] == "- invocation_id: `inv_1`"
    assert lines[3] == "- arguments_summary: 渲染 PDF"


def test_render_reflect_output_shape() -> None:
    reflect = ReflectTrace(summary="✅ PDF 已生成", verdict="ok")
    lines = _render_reflect(reflect)
    assert lines[0] == "**反思**:"
    assert lines[1] == "- summary: ✅ PDF 已生成"
    assert lines[2] == "- verdict: `ok`"


def test_render_spans_coalesces_token_deltas() -> None:
    spans = (
        SpanRecord(kind="reasoning_delta", started_at=1.0, summary={"token": "x"}),
        SpanRecord(kind="reasoning_delta", started_at=2.0, summary={"token": "y"}),
        SpanRecord(kind="hook_triggered", started_at=3.0, summary={"attempt": 1}),
    )
    lines = _render_spans(spans)
    joined = "\n".join(lines)
    assert "<details>" in lines
    assert "诊断 (3 spans，2 条 token 已 coalesce)" in joined
    assert "reasoning_delta" in joined
    assert "hook_triggered" in joined
