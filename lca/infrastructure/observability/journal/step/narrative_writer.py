"""StepNarrativeWriter —— JournalDocument → narrative.md 投影(ADR-0164 草案 Phase 4)。

对比旧 NarrativeSidecar:
    - **输入不同**: 接收 ``JournalDocument``(完整 step-tree), 不是流式事件。
    - **结构不同**: 每个 step 一节, 5 原语 (context_before / thinking / tool_call /
      tool_result / reflect) 子节, spans 折叠在 ``<details>``。
    - **不写流水**: 不再用 on_event 追加, 一次性写出整个 run 的叙事。

形态: ``traces/runs/<run_id>/narrative.md``

结构:
    # Run Narrative —— <objective>
    > run_id / trace_id / 4 分50 秒 / 9 步 / outcome

    ## 📊 Summary
    | step | phase | duration | outcome | 摘要 |
    | 1 | perceive | 12s | ok | ... |
    | ... |
    | 6 | act | 22s | ❌ fail | LayoutError ... |
    | ... |

    ## 🔍 Steps 详述
    ### Step 1: perceive (12s) ✓
    **上下文**: objective, attachments, prior_summary_chain
    **思考**: model, decision, reasoning
    **工具调用**: name, invocation_id, arguments_summary
    **工具结果**: ok, delta_summary, files_created, error
    **反思**: summary
    **诊断** (N spans, 折叠): ...

不做的事:
    - 不读 evidence(由 reader 按需 fetch)。
    - 不发 SSE / OTel。 纯文件投影。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lca.contracts.models.observability.journal_doc import JournalDocument
from lca.contracts.models.observability.journal_step import (
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


def _short(value: Any, limit: int = 80) -> str:
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
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


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
    """spans 折叠在 <details>, 默认隐藏, 需要时展开。"""
    if not spans:
        return []
    return [
        "<details>",
        f"<summary>诊断 ({len(spans)} spans)</summary>",
        "",
        *[f"- `{s.kind}` @ {_format_ts(s.started_at)}: {_short(s.summary, 120)}" for s in spans],
        "",
        "</details>",
    ]


# ── Step 完整渲染 ── ──


def _render_step(step: JournalStep) -> list[str]:
    phase_icon = _PHASE_EMOJI.get(step.phase, "·")
    outcome_icon = _OUTCOME_ICON.get(step.outcome)
    duration = _format_duration(step.duration_ms)
    title = f"### Step {step.step_index}: {phase_icon} {step.phase} ({duration}) {outcome_icon}"
    lines = [title, ""]
    if step.parent_step_id:
        lines.append(f"_parent: {step.parent_step_id}_")
    if step.subagent_role:
        lines.append(f"_subagent: {step.subagent_role}_")
    if step.error:
        lines.append(f"_error: `{_short(step.error, 200)}`_")
    lines.append("")
    if step.context_before is not None:
        lines.extend(_render_context(step))
    else:
        lines.append("**上下文**: _(未填)_")
    lines.append("")
    if step.thinking is not None:
        lines.extend(_render_thinking(step.thinking))
        lines.append("")
    if step.tool_call is not None:
        lines.extend(_render_tool_call(step.tool_call))
        lines.append("")
    if step.tool_result is not None:
        lines.extend(_render_tool_result(step.tool_result))
        lines.append("")
    if step.reflect is not None:
        lines.extend(_render_reflect(step.reflect))
        lines.append("")
    if step.spans:
        lines.extend(_render_spans(step.spans))
        lines.append("")
    return lines


# ── Summary 表 ── ──


def _render_summary(doc: JournalDocument) -> list[str]:
    lines = ["## 📊 Summary", ""]
    lines.append(f"- objective: `{_short(doc.metadata.objective, 200)}`")
    lines.append(f"- outcome: **{doc.metadata.outcome}**")
    if doc.started_at and doc.closed_at:
        dur_ms = int((doc.closed_at - doc.started_at) * 1000)
        lines.append(f"- total_duration: {_format_duration(dur_ms)}")
    lines.append(f"- total_steps: {len(doc.steps)}")
    # 失败计数
    fails = [s for s in doc.steps if s.outcome == "fail"]
    if fails:
        lines.append(f"- failed_steps: {len(fails)} (indexes: {[s.step_index for s in fails]})")
    # 文件累加
    files = doc.cumulative_files()
    if files:
        lines.append(f"- files_produced: {len(files)}")
    lines.append("")
    # 表格
    lines.append("| # | phase | duration | outcome | 摘要 |")
    lines.append("|---|---|---|---| |")
    for s in doc.steps:
        outcome_icon = _OUTCOME_ICON.get(s.outcome)
        outcome_str = f"{outcome_icon} {s.outcome}" if s.outcome else "· in progress"
        # 摘要 = reflect.summary / tool_result.delta_summary / thinking.decision
        summary = "—"
        if s.reflect is not None and s.reflect.summary:
            summary = _short(s.reflect.summary, 60)
        elif s.tool_result is not None and s.tool_result.delta_summary:
            summary = _short(s.tool_result.delta_summary, 60)
        elif s.thinking is not None and s.thinking.decision:
            summary = f"[{s.thinking.decision}]"
        elif s.tool_call is not None:
            summary = _short(s.tool_call.arguments_summary, 60)
        lines.append(
            f"| {s.step_index} "
            f"| {s.phase} "
            f"| {_format_duration(s.duration_ms)} "
            f"| {outcome_str} "
            f"| {_short(summary, 80)} |"
        )
    lines.append("")
    # 因果链
    lines.append("## 🔗 因果链 (prior_summary_chain)")
    lines.append("")
    chain = doc.prior_summary_chain()
    if chain:
        for i, s in enumerate(chain, 1):
            lines.append(f"{i}. {_short(s, 200)}")
    else:
        lines.append("_(空)_")
    return lines


# ── 顶层 ── ──


class StepNarrativeWriter:
    """把 JournalDocument 一次性写 narrative.md。

    用法:
        writer = StepNarrativeWriter(path)
        writer.write(document)
    """

    def __init__(self, output_path: str | Path) -> None:
        self._path = Path(output_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def output_path(self) -> Path:
        return self._path

    def write(self, document: JournalDocument) -> Path:
        """写 narrative.md。 返回落盘路径。"""
        text = self.render(document)
        self._path.write_text(text, encoding="utf-8")
        return self._path

    def render(self, document: JournalDocument) -> str:
        """纯函数 —— 给 document 返回 markdown 文本(测试 / CLI 直接 print 用)。"""
        lines: list[str] = []
        # 头
        lines.append(f"# Run Narrative —— {document.metadata.objective}")
        lines.append("")
        lines.append(
            f"> run_id=`{document.run_id}` trace_id=`{document.trace_id}` "
            f"started_at={_format_ts(document.started_at)} "
            f"closed_at={_format_ts(document.closed_at)}"
        )
        lines.append("")
        # summary
        lines.extend(_render_summary(document))
        lines.append("")
        # 详述
        lines.append("## 🔍 Steps 详述")
        lines.append("")
        for step in document.steps:
            lines.extend(_render_step(step))
        # 落款
        lines.append("---")
        lines.append(
            f"_generated by StepNarrativeWriter at {_format_ts_to_now()} — "
            f"schema={document.schema}_"
        )
        return "\n".join(lines) + "\n"


def _format_ts_to_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


__all__ = ["StepNarrativeWriter"]
