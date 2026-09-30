"""Step 子节渲染器 —— 5 原语 (context_before / thinking / tool_call /
tool_result / reflect) 与 spans 的 markdown 段落生成(ADR-0164 Phase 4)。

本模块只负责单个 step 的「子节」渲染;整步组装 ``_render_step`` 与
``StepNarrativeWriter`` 编排见 ``writer.py``,ADR-0185 fold 章节见
``fold.py``。所有函数为包内私有,经 writer 组装后对外。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lca.contracts.models.observability.journal.step import (
    JournalStep,
    ReflectTrace,
    SpanRecord,
    ThinkingTrace,
    ToolCallRecord,
    ToolResult,
)

# ── Phase emoji ──


_PHASE_EMOJI: dict[str, str] = {
    "perceive": "🔍",
    "think": "🧠",
    "act": "⚙️",
    "reflect": "🪞",
    "remember": "💭",
    "stop": "🛑",
}

_OUTCOME_ICON: dict[str | None, str] = {
    "ok": "✓",
    "fail": "✗",
    "skip": "→",
    None: "·",
}


def _short(value: object, limit: int = 80) -> str:
    """安全截断, 用于 markdown 表格里。"""
    if value is None:
        return ""
    text = str(value).replace("\n", "⏎").replace("\t", "⇥")
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def _format_duration(duration_ms: int | None) -> str:
    if duration_ms is None:
        return "—"
    if duration_ms < 1000:
        return f"{duration_ms}ms"
    seconds = duration_ms / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    return f"{seconds / 60:.1f}m"


def _format_ts(epoch: float | None) -> str:
    if epoch is None:
        return "—"
    return datetime.fromtimestamp(epoch, tz=UTC).strftime("%Y-%m-%d %H:%M:%SZ")


# ── Step 子节渲染 ── ──


def _render_context(step: JournalStep) -> list[str]:
    if step.context_before is None:
        return ["**上下文**: _(未填)_", ""]
    ctx = step.context_before
    lines = ["**上下文**:"]
    lines.append(f"- objective: `{_short(ctx.objective, 200)}`")
    if ctx.attachments:
        att_names = ", ".join(f"`{a.name}` ({a.size_bytes} B)" for a in ctx.attachments)
        lines.append(f"- attachments: {att_names}")
    if ctx.prior_summary_chain:
        # 展示最近 3 条 + 总数
        recent = ctx.prior_summary_chain[-3:]
        prefix = "..." if len(ctx.prior_summary_chain) > 3 else ""
        lines.append(f"- prior_summary_chain ({len(ctx.prior_summary_chain)} 条):")
        for s in recent:
            lines.append(f"  - {_short(s, 200)}")
        if prefix:
            lines.append(f"  - {prefix}")
    if ctx.cumulative_files:
        files = ", ".join(f"`{Path(f).name}`" for f in ctx.cumulative_files)
        lines.append(f"- cumulative_files: {files}")
    if ctx.extra:
        extra_str = ", ".join(f"{k}={_short(v, 40)}" for k, v in ctx.extra.items())
        lines.append(f"- extra: {extra_str}")
    return lines


def _render_thinking(trace: ThinkingTrace) -> list[str]:
    lines = ["**思考**:"]
    lines.append(f"- model: `{trace.model}` ({trace.latency_ms}ms)")
    if trace.prompt_tokens is not None or trace.completion_tokens is not None:
        lines.append(f"- tokens: prompt={trace.prompt_tokens} completion={trace.completion_tokens}")
    if trace.decision:
        lines.append(f"- decision: `{trace.decision}`")
    if trace.reasoning:
        lines.append(f"- reasoning: {_short(trace.reasoning, 400)}")
    if trace.raw_response_preview:
        lines.append(f"- response_preview: {_short(trace.raw_response_preview, 400)}")
    if trace.tool_call is not None:
        tc = trace.tool_call
        lines.append(f"- tool_call (decision): `{tc.name}` ({_short(tc.arguments_summary, 100)})")
    return lines


def _render_tool_call(call: ToolCallRecord) -> list[str]:
    return [
        "**工具调用**:",
        f"- name: `{call.name}`",
        f"- invocation_id: `{call.invocation_id}`",
        f"- arguments_summary: {_short(call.arguments_summary, 200)}",
    ]


def _render_tool_result(result: ToolResult) -> list[str]:
    lines = [
        f"**工具结果**: {'✓ ok' if result.ok else '✗ fail'}",
    ]
    lines.append(f"- latency_ms: {result.latency_ms}")
    if result.delta_summary:
        lines.append(f"- delta_summary: {_short(result.delta_summary, 200)}")
    if result.stdout_head:
        lines.append(f"- stdout_head: `{_short(result.stdout_head, 200)}`")
    lines.append(f"- stdout_chars_total: {result.stdout_chars_total}")
    if result.stdout_truncated:
        lines.append("- stdout_truncated: True")
    if result.stderr:
        lines.append(f"- stderr: `{_short(result.stderr, 300)}`")
    if result.files_created:
        files = ", ".join(f"`{f}`" for f in result.files_created)
        lines.append(f"- files_created: {files}")
    if result.error:
        lines.append(f"- error: `{_short(result.error, 300)}`")
    return lines


def _render_reflect(reflect: ReflectTrace) -> list[str]:
    lines = ["**反思**:"]
    lines.append(f"- summary: {_short(reflect.summary, 200)}")
    if reflect.verdict:
        lines.append(f"- verdict: `{reflect.verdict}`")
    if reflect.extra:
        extra = ", ".join(f"{k}={_short(v, 60)}" for k, v in reflect.extra.items())
        lines.append(f"- extra: {extra}")
    return lines


def _render_spans(spans: tuple[SpanRecord, ...]) -> list[str]:
    """spans 折叠在 <details>，默认隐藏，需要时展开（ADR-0166 D4b）。

    合并 ``reasoning_delta`` 类的 per-token span 为单条 summary，避免
    narrative 被几十~几百行 ``reasoning_delta`` 刷屏。其余按原样。
    """
    if not spans:
        return []
    token_kinds = {"reasoning_delta", "step_text_delta"}
    collapsed = [s for s in spans if s.kind in token_kinds]
    others = [s for s in spans if s.kind not in token_kinds]
    bullets: list[str] = []
    if collapsed:
        sample = collapsed[0]
        bullets.append(
            f"- `{sample.kind}` × {len(collapsed)} 条 token 增量（已合并 / 详见 evidence）"
        )
    for s in others:
        bullets.append(f"- `{s.kind}` @ {_format_ts(s.started_at)}: {_short(s.summary, 120)}")
    summary = f"诊断 ({len(spans)} spans"
    if collapsed:
        summary += f"，{len(collapsed)} 条 token 已 coalesce"
    summary += ")"
    return [
        "<details>",
        f"<summary>{summary}</summary>",
        "",
        *bullets,
        "",
        "</details>",
    ]
