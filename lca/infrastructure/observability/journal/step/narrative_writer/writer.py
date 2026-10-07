"""StepNarrativeWriter 编排 —— JournalDocument → narrative.md 的顶层组装。

包含整步组装 ``_render_step``、Summary 表 ``_render_summary`` 与
``StepNarrativeWriter`` 类(render / write / fold_provider seam)。5 原语
子节渲染器见 ``sections.py``,ADR-0185 fold 章节见 ``fold.py``。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from lca.contracts.models.observability.journal.doc import JournalDocument
from lca.contracts.models.observability.journal.step import JournalStep
from lca.infrastructure.atomic.write import atomic_write_text
from lca.infrastructure.observability.journal.step.narrative_writer.fold import (
    _render_fold_chapters,
)
from lca.infrastructure.observability.journal.step.narrative_writer.sections import (
    _OUTCOME_ICON,
    _PHASE_EMOJI,
    _format_duration,
    _format_ts,
    _render_context,
    _render_reflect,
    _render_spans,
    _render_thinking,
    _render_tool_call,
    _render_tool_result,
    short_text,
)
from lca.infrastructure.observability.replay.fold_source import FoldProvider
from lca.infrastructure.observability.spine.sinks.naming import spine_filename_for_run

if TYPE_CHECKING:
    from lca.infrastructure.observability.replay.fold_source import FoldedModelVisible

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
        lines.append(f"_error: `{short_text(step.error, 200)}`_")
    lines.append("")
    if step.context_before is not None:
        lines.extend(_render_context(step))
    else:
        lines.append("**上下文**: _(未填)_")
    lines.append("")
    if step.thinking is not None:
        lines.extend(_render_thinking(step.thinking))
        lines.append("")
    # 一个 decision 可一次发出多个 tool call（run_04457e1757b1 实测：同一
    # turn 内 update_assistant_profile + update_identity）。单数字段只保留首个
    # 调用，narrative 必须渲染全量 tool_calls，否则调用会"失踪"。
    calls = step.tool_calls or ((step.tool_call,) if step.tool_call is not None else ())
    results = step.tool_results or (
        (step.tool_result,) if step.tool_result is not None else ()
    )
    results_by_invocation = {r.invocation_id: r for r in results}
    for call in calls:
        lines.extend(_render_tool_call(call))
        matched = results_by_invocation.get(call.invocation_id)
        if matched is not None:
            lines.extend(_render_tool_result(matched))
        lines.append("")
    call_ids = {c.invocation_id for c in calls}
    for result in results:
        if result.invocation_id not in call_ids:
            lines.extend(_render_tool_result(result))
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
    lines.append(f"- objective: `{short_text(doc.metadata.objective, 200)}`")
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
            summary = short_text(s.reflect.summary, 60)
        elif s.tool_result is not None and s.tool_result.delta_summary:
            summary = short_text(s.tool_result.delta_summary, 60)
        elif s.thinking is not None and s.thinking.decision:
            summary = f"[{s.thinking.decision}]"
        elif s.tool_calls:
            summary = "; ".join(short_text(c.arguments_summary, 60) for c in s.tool_calls)
        elif s.tool_call is not None:
            summary = short_text(s.tool_call.arguments_summary, 60)
        lines.append(
            f"| {s.step_index} "
            f"| {s.phase} "
            f"| {_format_duration(s.duration_ms)} "
            f"| {outcome_str} "
            f"| {short_text(summary, 80)} |"
        )
    lines.append("")
    # 因果链
    lines.append("## 🔗 因果链 (prior_summary_chain)")
    lines.append("")
    chain = doc.prior_summary_chain()
    if chain:
        for i, summary in enumerate(chain, 1):
            lines.append(f"{i}. {short_text(summary, 200)}")
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
        # fold_source 是 in-repo 模块(仅 stdlib + lca/lca_kernel,无可选第三方
        # 依赖);本模块已从同一 infrastructure 树做模块级 import —— 此处
        # ImportError 不可达,不吞异常,让真实导入失败直接暴露。
        from lca.infrastructure.observability.replay.fold_source import (
            fold_model_visible,
        )
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
        lines.append(f"# Run Narrative —— {short_text(document.metadata.objective, 120)}")
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


__all__ = ["StepNarrativeWriter"]
