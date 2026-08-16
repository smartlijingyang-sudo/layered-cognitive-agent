"""FactStreamProjector —— journal 事实流投影器（DSH「模型所见即日志」终端视图）。

每个盖章事件作为一条「事实」渲染：事件类型 + 关键字段 + 时间戳。
InsightEngine 产出的 RunInsight 单独标记为「观察」——事实推导出的洞察。

设计原则（对齐 ADR-0037 + DSH session log philosophy）：
- 模型可见的即被记录的：每个事件都渲染，不做过滤
- 事实（fact）与观察（observation）分离：RunInsight 用不同标记
- 容器事件（run start/finish）用 Run Card 包裹

与 ConsoleJournalProjector 的区别：
- ConsoleJournalProjector 是「叙事视图」：聚合后只渲染一行摘要
- FactStreamProjector 是「事实流视图」：每个事件完整呈现，用于 debug 和审计

结构层次（对齐 DSH Trajectory 的 Turn→Step→Record 层次）：
- Run Card：Team/Agent run 边界，一步呈现成员/策略/任务
- Step Group：以 step 编号分组，视觉上缩进嵌套
- 资源嵌套：LLM call → Tool call 在同一 step 内缩进关联
- 相对计时：Δms 显示事件间距（对齐 DSH 每记录 duration 列）
- Token 累计：running total 在 LLM 完成时更新
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import TYPE_CHECKING

from lca.contracts.models.observability.journal import (
    ActionDegraded,
    AgentRunFinished,
    AgentRunStarted,
    AttachmentStagingCompleted,
    AttachmentStagingFailed,
    AttachmentStagingStarted,
    CastingCompleted,
    CastingFailed,
    CastingStarted,
    DecisionMade,
    DelegationCacheHit,
    DelegationCompleted,
    DelegationIssued,
    JournalEvent,
    LlmCallCompleted,
    LlmCallStarted,
    ReasoningCompleted,
    ReasoningDelta,
    RunActivity,
    RunInsight,
    SandboxOutputDelta,
    StampedEvent,
    StepCompleted,
    StepTextDelta,
    SynthesisCompleted,
    TeamRunFinished,
    TeamRunStarted,
    ToolCallStreaming,
    ToolDenied,
    ToolInvoked,
    ToolStarted,
)
from lca.contracts.protocols import JournalProjector

if TYPE_CHECKING:
    from typing import TextIO

# ── 渲染宽度 ──────────────────────────────────────────
_PREVIEW_MAX = 200
"""verbose 模式预览字段最大字符数。"""
_LINE_WIDTH = 72
"""结构化块边框宽度。"""


# ── 事件分类标记 ──────────────────────────────────────
_CONTAINER_ICONS = {"start": "▶", "finish": "■", "cast": "◎"}
_FACT_ICONS = {
    "decision": "◆",
    "step": "▸",
    "degrade": "⚠",
    "delegation_send": "⇢",
    "delegation_recv": "⇠",
    "delegation_hit": "⇢",
    "synthesis": "◈",
}
_OBSERVATION_ICONS = {
    "llm_start": "○",
    "llm_done": "●",
    "tool_start": "⬚",
    "tool_done": "✓",
    "tool_denied": "⛔",
    "tool_streaming": "⬚",
    "activity": "·",
}
_DELTA_ICONS = {
    "text_delta": "≋",
    "reasoning_delta": "≋",
    "reasoning_done": "≋",
    "sandbox_delta": "≋",
}
_INSIGHT_ICON = "💡"
_ATTACHMENT_ICONS = {
    "start": "📎",
    "done": "📎",
    "fail": "📎✗",
}


class FactStreamProjector(JournalProjector):
    """journal → terminal 事实流。每个事件一条事实，insight 标记为观察。

    结构化层次（对齐 DSH Trajectory）：
    - Run Card：Team/Agent 容器事件渲染为卡片
    - Step Group：step 变化时输出分组头
    - 资源嵌套：LLM + Tool 在 step 内缩进
    - 相对计时：Δms 标注事件间距

    ``verbose=True`` 显示预览字段（prompt/response/arguments/result）。
    ``show_deltas=True`` 显示增量事件（StepTextDelta / ReasoningDelta 等）。
    """

    def __init__(
        self,
        *,
        stream: TextIO | None = None,
        verbose: bool = False,
        show_deltas: bool = False,
    ) -> None:
        self._stream = stream if stream is not None else sys.stdout
        self._verbose = verbose
        self._show_deltas = show_deltas
        self._last_role: str | None = None
        self._last_ts: float | None = None
        self._run_start_ts: float | None = None
        self._current_step: int | None = None
        # Token 累计（对齐 DSH session cumulative usage）
        self._total_prompt_tokens: int = 0
        self._total_completion_tokens: int = 0
        self._total_llm_calls: int = 0
        self._total_tool_calls: int = 0
        self._total_tool_errors: int = 0
        # 事件渲染注册表
        self._renderers: dict[type[JournalEvent], Callable[[StampedEvent, JournalEvent], None]] = {
            TeamRunStarted: self._render_team_started,
            TeamRunFinished: self._render_team_finished,
            AgentRunStarted: self._render_agent_started,
            AgentRunFinished: self._render_agent_finished,
            CastingStarted: self._render_casting_started,
            CastingCompleted: self._render_casting_completed,
            CastingFailed: self._render_casting_failed,
            DelegationIssued: self._render_delegation_issued,
            DelegationCompleted: self._render_delegation_completed,
            DelegationCacheHit: self._render_delegation_cache_hit,
            SynthesisCompleted: self._render_synthesis_completed,
            DecisionMade: self._render_decision,
            StepCompleted: self._render_step_completed,
            ActionDegraded: self._render_action_degraded,
            LlmCallStarted: self._render_llm_started,
            LlmCallCompleted: self._render_llm_completed,
            ToolStarted: self._render_tool_started,
            ToolInvoked: self._render_tool_invoked,
            ToolDenied: self._render_tool_denied,
            ToolCallStreaming: self._render_tool_streaming,
            RunActivity: self._render_activity,
            RunInsight: self._render_insight,
            StepTextDelta: self._render_text_delta,
            ReasoningDelta: self._render_reasoning_delta,
            ReasoningCompleted: self._render_reasoning_completed,
            SandboxOutputDelta: self._render_sandbox_delta,
            AttachmentStagingStarted: self._render_attachment_started,
            AttachmentStagingCompleted: self._render_attachment_completed,
            AttachmentStagingFailed: self._render_attachment_failed,
        }

    # ── JournalProjector ───────────────────────────────
    def on_event(self, stamped: StampedEvent) -> None:
        event = stamped.event
        # 记录 run 起始时间（用于绝对偏移计算）
        if self._run_start_ts is None:
            self._run_start_ts = stamped.ts
        renderer = self._renderers.get(type(event))
        if renderer is not None:
            renderer(stamped, event)
        self._last_ts = stamped.ts

    def flush(self) -> None:
        self._stream.flush()

    def close(self) -> None:
        self.flush()

    # ── 时间与步进 ─────────────────────────────────────
    def _delta_ms(self, stamped: StampedEvent) -> str:
        """相对前一事件的 Δms。"""
        if self._last_ts is None:
            return "+0ms"
        delta = (stamped.ts - self._last_ts) * 1000
        return _format_duration(delta)

    def _offset_ms(self, stamped: StampedEvent) -> str:
        """距 run 起始的绝对偏移。"""
        if self._run_start_ts is None:
            return "0ms"
        offset = (stamped.ts - self._run_start_ts) * 1000
        return _format_duration(offset)

    def _step_group(self, stamped: StampedEvent, step: int) -> None:
        """step 变化时输出分组头（对齐 DSH 的 Step grouping）。"""
        if step != self._current_step:
            self._current_step = step
            self._emit(f"  ┌─ Step {step} ──────────────────────────────────")

    def _token_summary(self) -> str:
        """累计 token 摘要（对齐 DSH session cumulative usage）。"""
        return (
            f"tokens: {self._total_prompt_tokens + self._total_completion_tokens}"
            f" total "
            f"({self._total_prompt_tokens} in → {self._total_completion_tokens} out)"
        )

    # ── 容器事件 ───────────────────────────────────────
    def _render_team_started(self, stamped: StampedEvent, event: TeamRunStarted) -> None:
        self._section(stamped)
        members = ", ".join(event.members) if event.members else "—"
        lines = [
            "",
            f"═══ {_CONTAINER_ICONS['start']} TeamRun · {event.team_id} "
            f"{'═' * max(0, _LINE_WIDTH - 20 - len(event.team_id))}",
            f"│ strategy: {event.strategy_key}"
            f"  mandate: {event.mandate or '—'}"
            f"  lead: {event.lead_role or '—'}",
            f"│ members: {members}",
        ]
        if event.objective_preview:
            lines.append(f"│ task: {event.objective_preview}")
        if event.plan_steps:
            lines.append(f"│ plan: {event.plan_steps}")
        lines.append(f"{'═' * _LINE_WIDTH}")
        self._emit("\n".join(lines))
        # 重置累计
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._total_llm_calls = 0
        self._total_tool_calls = 0
        self._total_tool_errors = 0
        self._current_step = None

    def _render_team_finished(self, stamped: StampedEvent, event: TeamRunFinished) -> None:
        self._section(stamped)
        mark = "✓" if event.status == "completed" else "✗"
        elapsed = self._offset_ms(stamped)
        lines = [
            f"{'─' * _LINE_WIDTH}",
            f"  {_CONTAINER_ICONS['finish']} TeamRun {mark} {event.status}"
            f" · {event.steps} steps · {elapsed}",
        ]
        if self._total_llm_calls > 0:
            lines.append(f"  LLM: {self._total_llm_calls} calls · {self._token_summary()}")
        if self._total_tool_calls > 0:
            err = f" · {self._total_tool_errors} errors" if self._total_tool_errors else ""
            lines.append(f"  Tools: {self._total_tool_calls} calls{err}")
        if event.error:
            lines.append(f"  error: {_truncate(event.error, 80)}")
        lines.append(f"{'─' * _LINE_WIDTH}")
        self._emit("\n".join(lines))

    def _render_agent_started(self, stamped: StampedEvent, event: AgentRunStarted) -> None:
        self._section(stamped)
        line = (
            f"  {_CONTAINER_ICONS['start']} AgentRun [{self._delta_ms(stamped)}] {event.agent_role}"
        )
        if event.from_role:
            line += f" ← {event.from_role}"
        if event.objective_preview:
            line += f" · {_truncate(event.objective_preview, 60)}"
        self._emit(line)

    def _render_agent_finished(self, stamped: StampedEvent, event: AgentRunFinished) -> None:
        self._section(stamped)
        mark = "✓" if event.status == "completed" else "✗"
        elapsed = self._delta_ms(stamped)
        line = (
            f"  {_CONTAINER_ICONS['finish']} AgentRun {mark}"
            f" [{elapsed}] "
            f"{stamped.scope.agent_role} · {event.status} · {event.steps} steps"
        )
        if event.error:
            line += f" · error: {_truncate(event.error, 60)}"
        self._emit(line)

    # ── 选角 ───────────────────────────────────────────
    def _render_casting_started(self, stamped: StampedEvent, event: CastingStarted) -> None:
        self._section(stamped)
        self._emit(
            f"  {_CONTAINER_ICONS['cast']} casting started"
            f" [{self._delta_ms(stamped)}] · {event.objective_preview}"
        )

    def _render_casting_completed(self, stamped: StampedEvent, event: CastingCompleted) -> None:
        self._section(stamped)
        roles = "、".join(event.selected_roles)
        line = (
            f"  {_CONTAINER_ICONS['cast']} casting done"
            f" [{self._delta_ms(stamped)}] · {event.governance_kind}"
        )
        if event.lead_role:
            line += f" · lead: {event.lead_role}"
        line += f" · {roles}"
        self._emit(line)
        if self._verbose and event.rationale:
            self._emit(f"    rationale: {_truncate(event.rationale, _PREVIEW_MAX)}")

    def _render_casting_failed(self, stamped: StampedEvent, event: CastingFailed) -> None:
        self._section(stamped)
        self._emit(
            f"  {_CONTAINER_ICONS['cast']} casting FAILED"
            f" [{self._delta_ms(stamped)}] · {event.error}"
        )

    # ── 协作事件 ───────────────────────────────────────
    def _render_delegation_issued(self, stamped: StampedEvent, event: DelegationIssued) -> None:
        self._section(stamped)
        mech_val = (
            event.mechanism.value if hasattr(event.mechanism, "value") else str(event.mechanism)
        )
        mech = f" [{mech_val}]" if mech_val != "delegate" else ""
        lines = [
            f"  {_FACT_ICONS['delegation_send']} delegation →"
            f" {event.callee_role}{mech} [{self._delta_ms(stamped)}]",
            f"    subtask: {_truncate(event.subtask_preview, 100)}",
        ]
        self._emit("\n".join(lines))

    def _render_delegation_completed(
        self, stamped: StampedEvent, event: DelegationCompleted
    ) -> None:
        self._section(stamped)
        mark = "ok" if event.ok else "FAIL"
        line = (
            f"  {_FACT_ICONS['delegation_recv']} delegation ←"
            f" [{self._delta_ms(stamped)}] {mark} · {event.status}"
        )
        self._emit(line)
        if self._verbose and event.output_text:
            self._emit(f"    output: {_truncate(event.output_text, _PREVIEW_MAX)}")

    def _render_delegation_cache_hit(
        self, stamped: StampedEvent, event: DelegationCacheHit
    ) -> None:
        self._section(stamped)
        self._emit(
            f"  {_FACT_ICONS['delegation_hit']} delegation cache hit"
            f" [{self._delta_ms(stamped)}] · "
            f"{event.callee_role} · step {event.step}"
        )

    def _render_synthesis_completed(self, stamped: StampedEvent, event: SynthesisCompleted) -> None:
        self._section(stamped)
        self._emit(
            f"  {_FACT_ICONS['synthesis']} synthesis"
            f" [{self._delta_ms(stamped)}] · "
            f"{event.method} · {event.candidate_count} candidates"
        )

    # ── 认知事实 ───────────────────────────────────────
    def _render_decision(self, stamped: StampedEvent, event: DecisionMade) -> None:
        self._section(stamped)
        self._step_group(stamped, event.step)
        target = f" → {event.delegate_target}" if event.delegate_target else ""
        tool = f" ({event.tool_name})" if event.tool_name else ""
        conf = f" conf={event.confidence:.2f}" if event.confidence else ""
        lines = [
            f"  │ {_FACT_ICONS['decision']} decision"
            f" #{stamped.seq} {self._delta_ms(stamped)}{conf}",
            f"  │   action: {event.action_type}{tool}{target}",
        ]
        if event.rationale_preview:
            lines.append(f"  │   rationale: {_truncate(event.rationale_preview, 100)}")
        if self._verbose and event.response_text:
            lines.append(f"  │   response: {_truncate(event.response_text, _PREVIEW_MAX)}")
        self._emit("\n".join(lines))

    def _render_step_completed(self, stamped: StampedEvent, event: StepCompleted) -> None:
        self._section(stamped)
        self._step_group(stamped, event.step)
        self._emit(
            f"  │ {_FACT_ICONS['step']} step {event.step}"
            f" #{stamped.seq} {self._delta_ms(stamped)} "
            f"{event.status} · {event.action_type}"
        )

    def _render_action_degraded(self, stamped: StampedEvent, event: ActionDegraded) -> None:
        self._section(stamped)
        self._emit(
            f"  │ {_FACT_ICONS['degrade']} degraded"
            f" [{self._delta_ms(stamped)}] step={event.step} · "
            f"{event.original_action_type} → {event.degraded_to}"
        )

    # ── 资源事实：LLM（结构化块，对齐 DSH assistant timing）──
    def _render_llm_started(self, stamped: StampedEvent, event: LlmCallStarted) -> None:
        self._section(stamped)
        self._step_group(stamped, event.step)
        self._emit(
            f"  │ {_OBSERVATION_ICONS['llm_start']} llm.start"
            f" #{stamped.seq} {self._delta_ms(stamped)} "
            f"model={event.model}"
        )

    def _render_llm_completed(self, stamped: StampedEvent, event: LlmCallCompleted) -> None:
        self._section(stamped)
        # 更新 token 累计
        self._total_prompt_tokens += event.prompt_tokens
        self._total_completion_tokens += event.completion_tokens
        self._total_llm_calls += 1
        mark = "ok" if event.ok else "FAIL"
        stream = " stream" if event.stream else ""
        tokens = ""
        if event.prompt_tokens or event.completion_tokens:
            tokens = f" {event.prompt_tokens}→{event.completion_tokens} tok"
        lines = [
            f"  │ {_OBSERVATION_ICONS['llm_done']} llm.done"
            f" #{stamped.seq} {self._delta_ms(stamped)} "
            f"{event.model} · {event.latency_ms}ms{tokens}{stream} · {mark}",
        ]
        # 累计摘要（对齐 DSH session cumulative）
        if self._total_llm_calls > 1:
            lines.append(
                f"  │   cumulative: {self._token_summary()} over {self._total_llm_calls} calls"
            )
        if self._verbose:
            if event.prompt_preview:
                lines.append(f"  │   prompt: {_truncate(event.prompt_preview, _PREVIEW_MAX)}")
            if event.response_preview:
                lines.append(f"  │   response: {_truncate(event.response_preview, _PREVIEW_MAX)}")
        self._emit("\n".join(lines))

    # ── 资源事实：工具（结构化块，对齐 DSH tool detail）──
    def _render_tool_started(self, stamped: StampedEvent, event: ToolStarted) -> None:
        self._section(stamped)
        self._total_tool_calls += 1
        lines = [
            f"  │   {_OBSERVATION_ICONS['tool_start']} tool.start"
            f" #{stamped.seq} {self._delta_ms(stamped)} {event.tool_name}",
        ]
        if event.arguments_preview:
            lines.append(f"  │     args: {_truncate(event.arguments_preview, 100)}")
        if self._verbose and event.plugin_state:
            lines.append(f"  │     state: {_truncate(str(event.plugin_state), _PREVIEW_MAX)}")
        self._emit("\n".join(lines))

    def _render_tool_invoked(self, stamped: StampedEvent, event: ToolInvoked) -> None:
        self._section(stamped)
        mark = "ok" if event.ok else "FAIL"
        if not event.ok:
            self._total_tool_errors += 1
        lines = [
            f"  │   {_OBSERVATION_ICONS['tool_done']} tool.done"
            f" #{stamped.seq} {self._delta_ms(stamped)} "
            f"{event.tool_name} · {event.latency_ms}ms · {mark}",
        ]
        if event.error:
            lines.append(f"  │     error: {_truncate(event.error, 100)}")
        if self._verbose:
            if event.result_preview:
                lines.append(f"  │     result: {_truncate(event.result_preview, _PREVIEW_MAX)}")
            if event.plugin_state:
                lines.append(f"  │     state: {_truncate(str(event.plugin_state), _PREVIEW_MAX)}")
        self._emit("\n".join(lines))

    def _render_tool_denied(self, stamped: StampedEvent, event: ToolDenied) -> None:
        self._section(stamped)
        self._emit(
            f"  │   {_OBSERVATION_ICONS['tool_denied']} tool.denied"
            f" #{stamped.seq} {self._delta_ms(stamped)} "
            f"{event.tool_name} · {event.reason}"
        )

    def _render_tool_streaming(self, stamped: StampedEvent, event: ToolCallStreaming) -> None:
        self._section(stamped)
        line = (
            f"  │   {_OBSERVATION_ICONS['tool_streaming']} tool.streaming"
            f" #{stamped.seq} {self._delta_ms(stamped)} "
            f"{event.tool_name}"
        )
        if self._verbose and event.arguments_preview:
            line += f"\n  │     args: {_truncate(event.arguments_preview, 100)}"
        self._emit(line)

    # ── 活动心跳 ───────────────────────────────────────
    def _render_activity(self, stamped: StampedEvent, event: RunActivity) -> None:
        self._section(stamped)
        detail = f" · {event.detail}" if event.detail else ""
        self._emit(
            f"  │ {_OBSERVATION_ICONS['activity']} activity"
            f" #{stamped.seq} {self._delta_ms(stamped)} "
            f"phase={event.phase} step={event.step}{detail}"
        )

    # ── 增量事件（仅 verbose 或 show_deltas 时显示）─────
    def _render_text_delta(self, stamped: StampedEvent, event: StepTextDelta) -> None:
        if not self._show_deltas:
            return
        self._section(stamped)
        self._emit(
            f"  │   {_DELTA_ICONS['text_delta']} text.delta"
            f" #{stamped.seq} {self._delta_ms(stamped)} "
            f"step={event.step} ch={event.channel} seq={event.seq}: "
            f"{_truncate(event.text_delta, 80)}"
        )

    def _render_reasoning_delta(self, stamped: StampedEvent, event: ReasoningDelta) -> None:
        if not self._show_deltas:
            return
        self._section(stamped)
        self._emit(
            f"  │   {_DELTA_ICONS['reasoning_delta']} reasoning.delta"
            f" #{stamped.seq} {self._delta_ms(stamped)} "
            f"step={event.step} seq={event.seq}: "
            f"{_truncate(event.text_delta, 80)}"
        )

    def _render_reasoning_completed(self, stamped: StampedEvent, event: ReasoningCompleted) -> None:
        self._section(stamped)
        line = (
            f"  │   {_DELTA_ICONS['reasoning_done']} reasoning.done"
            f" #{stamped.seq} {self._delta_ms(stamped)} "
            f"step={event.step} · {event.duration_ms}ms"
        )
        if self._verbose and event.content_preview:
            line += f"\n  │     preview: {_truncate(event.content_preview, _PREVIEW_MAX)}"
        self._emit(line)

    def _render_sandbox_delta(self, stamped: StampedEvent, event: SandboxOutputDelta) -> None:
        if not self._show_deltas:
            return
        self._section(stamped)
        self._emit(
            f"  │   {_DELTA_ICONS['sandbox_delta']} sandbox.delta"
            f" #{stamped.seq} {self._delta_ms(stamped)} "
            f"{event.stream} seq={event.seq}: "
            f"{_truncate(event.text_delta, 80)}"
        )

    # ── 附件暂存 ───────────────────────────────────────
    def _render_attachment_started(
        self, stamped: StampedEvent, event: AttachmentStagingStarted
    ) -> None:
        self._section(stamped)
        self._emit(
            f"  {_ATTACHMENT_ICONS['start']} attach.start"
            f" [{self._delta_ms(stamped)}] "
            f"plane={event.plane_id} files={event.file_count}"
            f" bytes={event.total_bytes}"
        )

    def _render_attachment_completed(
        self, stamped: StampedEvent, event: AttachmentStagingCompleted
    ) -> None:
        self._section(stamped)
        self._emit(
            f"  {_ATTACHMENT_ICONS['done']} attach.done"
            f" [{self._delta_ms(stamped)}] "
            f"plane={event.plane_id} {event.duration_ms:.0f}ms"
        )

    def _render_attachment_failed(
        self, stamped: StampedEvent, event: AttachmentStagingFailed
    ) -> None:
        self._section(stamped)
        paths = ", ".join(event.failed_paths[:3]) if event.failed_paths else ""
        self._emit(
            f"  {_ATTACHMENT_ICONS['fail']} attach.FAIL"
            f" [{self._delta_ms(stamped)}] "
            f"plane={event.plane_id} · {event.error}" + (f" · {paths}" if paths else "")
        )

    # ── 观察（Insight）─────────────────────────────────
    def _render_insight(self, stamped: StampedEvent, event: RunInsight) -> None:
        self._section(stamped)
        lines = [
            f"  {_INSIGHT_ICON} observation [{self._delta_ms(stamped)}] kind={event.kind}",
            f"    {_truncate(event.summary, 120)}",
        ]
        if event.detail:
            lines.append(f"    detail: {_truncate(event.detail, 120)}")
        self._emit("\n".join(lines))

    # ── 工具方法 ───────────────────────────────────────
    def _section(self, stamped: StampedEvent) -> None:
        """角色切换时输出 section header。"""
        role = stamped.scope.agent_role
        if role and role != self._last_role:
            self._emit(f"\n── {role} ──")
            self._last_role = role
            self._current_step = None  # 角色切换时重置 step 分组

    def _emit(self, text: str) -> None:
        print(text, file=self._stream, flush=True)


# ── 工具函数 ──────────────────────────────────────────


def _truncate(text: str, max_len: int) -> str:
    """截断长文本。"""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _format_duration(ms: float) -> str:
    """格式化毫秒为人类可读的时长标签（对齐 DSH formatDurationMillis）。"""
    if ms < 1:
        return "+0ms"
    if ms < 1000:
        return f"+{ms:.0f}ms"
    if ms < 60_000:
        return f"+{ms / 1000:.1f}s"
    minutes = int(ms // 60_000)
    seconds = (ms % 60_000) / 1000
    return f"+{minutes}m{seconds:.0f}s"
