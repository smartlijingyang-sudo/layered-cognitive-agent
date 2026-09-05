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

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lca.contracts.models.observability.journal_doc import JournalDocument
from lca.contracts.models.observability.journal_step import (
    JournalStep,
    ReflectTrace,
    SpanRecord,
    ThinkingTrace,
    ToolCallRecord,
    ToolResult,
)
from lca.infrastructure.atomic_write import atomic_write_text
from lca.infrastructure.observability.spine.sinks.naming import spine_filename_for_run

if TYPE_CHECKING:
    from lca.infrastructure.observability.replay.fold_source import FoldedModelVisible

# Fold provider seam —— 每 step 调一次;返回 None 表示 fold SSOT 不可用,
# narrative 应优雅降级到 N/A 占位(不抛错、不影响其它章节)。test 用 mock
# callable 注入;production 走默认 ``fold_model_visible``(读 spine.jsonl)。
FoldProvider = Callable[[str, str], "FoldedModelVisible | None"]

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


# ── Fold 章节(ADR-0185 PR-3.1 narrative 增强) ── ──

_FOLD_NA = "_N/A (fold SSOT 不可用)_"
"""fold_provider 返回 None 时的占位串;章节数 / 标题保留,内容降级。"""


def _tool_name(tool: Any) -> str:
    """tool schema 的 name 字段,降级回退 attribute / key。"""
    if isinstance(tool, Mapping):
        value = tool.get("name")
        if value is not None:
            return str(value)
        fn = tool.get("function")
        if isinstance(fn, Mapping):
            nested = fn.get("name")
            if nested is not None:
                return str(nested)
    return getattr(tool, "name", None) or "<unnamed>"


def _tool_description(tool: Any) -> str:
    """tool schema 的 description,缺失降级空串。"""
    if isinstance(tool, Mapping):
        value = tool.get("description")
        if value is None:
            fn = tool.get("function")
            if isinstance(fn, Mapping):
                value = fn.get("description")
    else:
        value = getattr(tool, "description", None)
    return str(value) if value is not None else ""


def _render_tools_sent(fold: FoldedModelVisible | None) -> list[str]:
    """🧰 Tools sent to model(N) —— fold.header.tools 列表渲染。

    fold = None ⇒ 整段显示 N/A 占位(不抛错)。
    tools 为空 ⇒ 标题后显式「(空,本 step 未下发工具)」。
    """
    if fold is None or fold.header is None:
        return [f"**🧰 Tools sent to model(0)** — {_FOLD_NA}"]
    tools = fold.header.tools or ()
    lines = [f"**🧰 Tools sent to model({len(tools)})**"]
    if not tools:
        lines.append("- _(空,本 step 未下发工具)_")
        return lines
    for tool in tools:
        name = _tool_name(tool)
        desc = _short(_tool_description(tool), 60)
        if desc:
            lines.append(f"- `{name}` — {desc}")
        else:
            lines.append(f"- `{name}`")
    return lines


def _render_skills_activated(fold: FoldedModelVisible | None) -> list[str]:
    """🎯 Skills activated(N) —— fold.manifest.activated_skill_ids + available_skills_count。

    manifest 缺 / skill_router 未启用 ⇒ 显式标注「SkillRouter 未启用」。
    有 catalog 但无激活 ⇒ 标注「无匹配 (catalog=N)」。
    """
    if fold is None or fold.header is None:
        return [f"**🎯 Skills activated(0)** — {_FOLD_NA}"]
    manifest = fold.manifest or {}
    if "activated_skill_ids" not in manifest and "available_skills_count" not in manifest:
        return ["**🎯 Skills activated** — SkillRouter 未启用或本 step 未触发 prompt assembler"]
    activated = manifest.get("activated_skill_ids") or []
    catalog_count = manifest.get("available_skills_count")
    lines = [f"**🎯 Skills activated({len(activated)})**"]
    if catalog_count is not None:
        lines.append(f"- catalog 总数: {catalog_count}")
    if activated:
        for sid in activated:
            lines.append(f"- `{sid}`")
    else:
        if catalog_count:
            lines.append("- _(无匹配 / SkillRouter 已启用但本 step 未选中)_")
        else:
            lines.append("- _(SkillRouter 已启用,catalog 空)_")
    return lines


def _render_prompt_sections(fold: FoldedModelVisible | None) -> list[str]:
    """📚 Sections in prompt(N) —— fold.manifest.sections 列表渲染。

    字段:name + text_chars + content_digest 前 16(碰撞足够区分)。
    sections 缺失 ⇒ 标注「未携带 section trace(reasoner 降级路径)」。
    """
    if fold is None or fold.header is None:
        return [f"**📚 Sections in prompt(0)** — {_FOLD_NA}"]
    manifest = fold.manifest or {}
    sections = manifest.get("sections")
    if sections is None:
        return [
            "**📚 Sections in prompt** — 未携带 section trace(reasoner 降级路径或非 think step)"
        ]
    lines = [f"**📚 Sections in prompt({len(sections)})**"]
    for section in sections:
        if not isinstance(section, Mapping):
            lines.append(f"- {_short(section, 100)}")
            continue
        name = section.get("name", "<unnamed>")
        text_chars = section.get("text_chars")
        digest = section.get("content_digest") or ""
        digest_short = str(digest)[:16] if digest else "—"
        chars_str = f"{text_chars}" if text_chars is not None else "?"
        line = f"- `{name}` — text_chars={chars_str} digest={digest_short}"
        if section.get("skipped_empty"):
            line += " (skipped_empty)"
        if section.get("used_fallback"):
            line += " (used_fallback)"
        lines.append(line)
    return lines


def _render_context_items(fold: FoldedModelVisible | None) -> list[str]:
    """💬 Context items(N) —— fold.manifest.context_manifest_items 列表渲染。

    每项 kind + payload_preview[:120];无 manifest 路径 ⇒ 标注降级。
    """
    if fold is None or fold.header is None:
        return [f"**💬 Context items(0)** — {_FOLD_NA}"]
    manifest = fold.manifest or {}
    items = manifest.get("context_manifest_items")
    if items is None:
        return ["**💬 Context items** — 未携带 context_manifest(not Hub 路径 / 降级)"]
    lines = [f"**💬 Context items({len(items)})**"]
    for item in items:
        if not isinstance(item, Mapping):
            lines.append(f"- {_short(item, 120)}")
            continue
        kind = item.get("kind", "<unknown>")
        preview = _short(item.get("payload_preview", ""), 120)
        if preview:
            lines.append(f"- `{kind}` — {preview}")
        else:
            lines.append(f"- `{kind}`")
    return lines


def _render_reasoning_per_step(fold: FoldedModelVisible | None) -> list[str]:
    """🧠 Reasoning per step —— SpineLlmRequestHeaderAssistantPayload.assistant_content。

    fold.assistant 为 None ⇒ 标注「assistant payload 缺失」;空字符串
    视为「模型直接调用工具 / 无文字回复」。
    """
    if fold is None or fold.header is None:
        return [f"**🧠 Reasoning per step** — {_FOLD_NA}"]
    assistant = fold.assistant
    if assistant is None:
        return ["**🧠 Reasoning per step** — assistant payload 缺失(post hook 未跑 / skip)"]
    content = getattr(assistant, "assistant_content", "") or ""
    if not content:
        return ["**🧠 Reasoning per step** — _(空,模型直接调用工具 / 无文字回复)_"]
    # 不截断 reasoning;落地即为真值(总字数限制在调用方 enforce)
    return ["**🧠 Reasoning per step**", "", content]


def _render_fold_chapters(
    fold: FoldedModelVisible | None,
    *,
    char_budget: int = 4000,
) -> list[str]:
    """聚合 5 个 fold 章节;超 char_budget 时整体截断。

    budget = 每 step 允许的 fold 章节总字数(per task spec);默认 4000。
    """
    sections: list[list[str]] = [
        _render_tools_sent(fold),
        _render_skills_activated(fold),
        _render_prompt_sections(fold),
        _render_context_items(fold),
        _render_reasoning_per_step(fold),
    ]
    out: list[str] = []
    used = 0
    truncated = False
    for section in sections:
        body = "\n".join(section)
        section_chars = len(body) + 1  # +1 for join newline
        if used + section_chars > char_budget and out:
            truncated = True
            break
        out.extend(section)
        out.append("")
        used += section_chars
    if truncated:
        out.append(f"_… (后续 fold 章节因 {char_budget} 字符上限截断;详见 fold SSOT)_")
    # 去掉末尾多余空行
    while out and out[-1] == "":
        out.pop()
    return out


# ── Step 完整渲染 ── ──


def _render_step(
    step: JournalStep,
    *,
    fold: FoldedModelVisible | None = None,
) -> list[str]:
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
    # ADR-0185 PR-3.1:narrative 增强 5 章节(从 fold SSOT 派生)。
    # fold = None ⇒ 每个子渲染器内部显式降级到 N/A 占位,此处不再
    # 全段跳过 —— 让用户看到「fold 不可用」的明示,而不是章节失踪。
    lines.extend(_render_fold_chapters(fold))
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
        # 注入自定义 fold_provider(测试用 mock / CLI 切换 source):
        writer = StepNarrativeWriter(path, fold_provider=my_loader)
    """

    def __init__(
        self,
        output_path: str | Path,
        *,
        fold_provider: FoldProvider | None = None,
    ) -> None:
        self._path = Path(output_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # 默认 fold_provider:读 ``<run_dir>/<run_id>.spine.jsonl`` →
        # FoldedModelVisible;无 spine / fold 返回 None 时,章节降级到
        # N/A 占位。CLI / 测试可注入 callable 替换(e.g. mock 返回固定
        # FoldedModelVisible,或截断 fold 跑 narrative 单元测试)。
        if fold_provider is None:
            self._fold_provider: FoldProvider = self._default_fold_provider
        else:
            self._fold_provider = fold_provider

    @property
    def output_path(self) -> Path:
        return self._path

    @property
    def fold_provider(self) -> FoldProvider:
        """当前 fold_provider;测试 seam 可读可替换。"""
        return self._fold_provider

    def _default_fold_provider(self, run_id: str, step_id: str) -> FoldedModelVisible | None:
        """production fold_provider —— 走 ``fold_model_visible`` 重建。

        输出路径无 run_dir(`StepNarrativeWriter("")`)⇒ 跳过 IO 探测,
        全部 step 走 N/A;非 production 跑 render() 的场景(如 unit
        测试直接调 ``writer.render(doc)`` 而不落盘)。
        """
        if self._path == Path() or self._path.parent == Path("."):
            return None
        try:
            from lca.infrastructure.observability.replay.fold_source import (
                fold_model_visible,
            )
        except ImportError:
            return None
        return fold_model_visible(
            run_dir=self._path.parent,
            run_id=run_id,
            step_id=step_id,
        )

    def write(self, document: JournalDocument) -> Path:
        """原子覆盖写 narrative.md。 返回落盘路径。"""
        text = self.render(document)
        return atomic_write_text(self._path, text)

    def render(self, document: JournalDocument) -> str:
        """纯函数 —— 给 document 返回 markdown 文本(测试 / CLI 直接 print 用)。"""
        lines: list[str] = []
        # 头 — totals 三数（ADR-0166 D1 / 0167 D11 narrative 形态）
        totals = getattr(document, "totals", None)
        total_str = (
            f"steps={totals.steps} segments={totals.segments} phases={totals.phases}"
            if totals is not None
            else f"total_steps={document.total_steps()}"
        )
        lines.append(f"# Run Narrative —— {_short(document.metadata.objective, 120)}")
        lines.append("")
        lines.append(
            f"> {total_str}  "
            f"run_id=`{document.run_id}` trace_id=`{document.trace_id}` "
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
        # ADR-0185 PR-4:Model saw 链接仅指向 spine fold SSOT;无 spine 时标注 unavailable。
        lines.append("### 🪞 Model saw (per step)")
        lines.append("")
        spine_exists = False
        spine_path: Path | None = None
        if self._path != Path() and self._path.parent != Path("."):
            spine_path = self._path.parent / spine_filename_for_run(document.run_id)
            spine_exists = spine_path.exists()
        for step in document.steps:
            if spine_exists and spine_path is not None:
                lines.append(
                    f"- `{step.step_id}` → "
                    f"`{spine_path}` (fold 重建;见 `lca_kernel.events.fold.foldRequestHeader`)"
                )
            else:
                lines.append(
                    f"- `{step.step_id}` → fold unavailable (no spine ledger; sidecar retired)"
                )
        lines.append("")
        for step in document.steps:
            # ADR-0185 PR-3.1:每 step 调 fold_provider 拿 FoldedModelVisible;
            # 任何异常 / None 返回都走 fold 子渲染器内置的 N/A 降级(不抛
            # 也不打断主 narrative 流程,守护 viewer / explain 可用性)。
            fold = self._safe_fold(document.run_id, step.step_id)
            lines.extend(_render_step(step, fold=fold))
        # 落款
        lines.append("---")
        lines.append(
            f"_generated by StepNarrativeWriter at {_format_ts_to_now()} — "
            f"schema={document.schema}_"
        )
        return "\n".join(lines) + "\n"

    def _safe_fold(self, run_id: str, step_id: str) -> FoldedModelVisible | None:
        """调 fold_provider,异常一律吞 → 返回 None(章节降级)。

        viewer / explain 用户的 narrative 永远要可读;fold 链路任何
        bug(IO / parse / spine 不在)都不应阻塞 narrative.md 落盘。
        """
        try:
            return self._fold_provider(run_id, step_id)
        except Exception:  # INTENTIONAL: fold 失败 ≠ narrative 失败
            return None


def _format_ts_to_now() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%SZ")


__all__ = ["FoldProvider", "StepNarrativeWriter"]
