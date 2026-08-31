"""ConsoleJournalProjector —— journal 驱动的框架默认人类视图（ADR-0037）。

替代 span 驱动的旧 console 导出器：叙事直接取自执行日志（真相层），
按 verbosity 分档：
- minimal：场景卡 + Run Card + 洞察/错误；
- standard：+ 关键叙事行（委派/决策/LLM/工具/综合，无预览）；
- verbose：+ LLM I/O 预览 + Mermaid 序列图。

并发安全：section 头按事件 scope 的角色推导，成员交错完成不串行。
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from lca.contracts.models.observability.journal import (
    ActionDegraded,
    AgentRunFinished,
    AgentRunStarted,
    CastingCompleted,
    CastingFailed,
    CastingStarted,
    DecisionMade,
    DelegationCacheHit,
    DelegationCompleted,
    DelegationIssued,
    JournalEvent,
    LlmCallCompleted,
    StampedEvent,
    SynthesisCompleted,
    TeamRunFinished,
    TeamRunStarted,
    ToolDenied,
    ToolInvoked,
)
from lca.contracts.protocols import JournalProjector
from lca.infrastructure.observability.adapters.policy import Verbosity
from lca.infrastructure.observability.journal.console import render as render
from lca.infrastructure.observability.journal.console.sequence_diagram import (
    render_sequence_diagram,
)

if TYPE_CHECKING:
    from typing import TextIO

_MAX_BUFFERED_TRACES = 64
"""并发 trace 缓冲上限（超出丢弃最旧，防内存膨胀）。"""


class _TraceState:
    """单个 trace 的聚合状态（console 内部累加器）。"""

    def __init__(self) -> None:
        self.is_team = False
        self.trace: dict[str, Any] = {}
        self.runs: dict[str, dict[str, Any]] = {}
        self.events: list[StampedEvent] = []
        self.last_section: str | None = None
        # 增量投影索引：委派事件的快速查找表（O(1) 替代 O(n) 线性扫描）
        self.delegation_issued: dict[str, StampedEvent] = {}


class ConsoleJournalProjector(JournalProjector):
    """journal → console：场景卡、角色叙事、Run Card、序列图。"""

    def __init__(self, verbosity: Verbosity = Verbosity.STANDARD, *, stream: TextIO | None = None):
        self._verbosity = verbosity
        self._stream = stream if stream is not None else sys.stdout
        self._traces: dict[str, _TraceState] = {}
        # 容器事件分派表（与 OtelProjector._handlers 同构）
        self._container_handlers: dict[type[JournalEvent], Callable] = {
            TeamRunStarted: self._on_team_run_started,
            TeamRunFinished: self._on_team_run_finished,
            AgentRunStarted: self._on_agent_run_started,
            AgentRunFinished: self._on_agent_run_finished,
        }
        # 叙事行渲染注册表（事件类型 → 渲染方法）
        self._narrative_renderers: dict[type[JournalEvent], Callable[..., str]] = {
            DelegationIssued: self._render_delegation_issued,
            DelegationCompleted: self._render_delegation_completed,
            DelegationCacheHit: self._render_delegation_cache_hit,
            LlmCallCompleted: self._render_llm_completed,
            ToolInvoked: self._render_tool_invoked,
            ToolDenied: self._render_tool_denied,
            DecisionMade: self._render_decision_made,
            SynthesisCompleted: self._render_synthesis_completed,
            ActionDegraded: self._render_action_degraded,
            CastingStarted: self._render_casting_started,
            CastingCompleted: self._render_casting_completed,
            CastingFailed: self._render_casting_failed,
        }

    # ── JournalProjector ───────────────────────────────
    def on_event(self, stamped: StampedEvent) -> None:
        state = self._state_of(stamped)
        state.events.append(stamped)
        event = stamped.event
        handler = self._container_handlers.get(type(event))
        if handler is not None:
            handler(stamped, event)
        else:
            self._on_narrative_event(stamped, event)

    def flush(self) -> None:
        self._stream.flush()

    def close(self) -> None:
        self.flush()

    # ── 容器事件 ───────────────────────────────────────
    def _on_team_run_started(self, stamped: StampedEvent, event: TeamRunStarted) -> None:
        state = self._state_of(stamped)
        state.is_team = True
        state.trace.update(
            {
                "team_id": event.team_id,
                "strategy_key": event.strategy_key,
                "title": event.team_id,
            }
        )
        state.runs.setdefault(stamped.scope.run_id, {}).update({"role": "(team)"})
        self._emit(
            render.render_scenario_card(
                {
                    "scope": "team",
                    "team_id": event.team_id,
                    "strategy_key": event.strategy_key,
                    "mandate": event.mandate,
                    "lead_role": event.lead_role,
                    "members": list(event.members),
                    "plan_steps": event.plan_steps,
                    "objective_preview": event.objective_preview,
                }
            )
        )

    def _on_team_run_finished(self, stamped: StampedEvent, event: TeamRunFinished) -> None:
        state = self._state_of(stamped)
        state.trace.update({"status": event.status, "steps": event.steps})
        self._finish_trace(stamped, state, error=event.error)

    def _on_agent_run_started(self, stamped: StampedEvent, event: AgentRunStarted) -> None:
        state = self._state_of(stamped)
        run = state.runs.setdefault(stamped.scope.run_id, {})
        run.update({"role": event.agent_role, "start_ts": stamped.ts})
        if not state.is_team and not stamped.scope.parent_run_id:
            state.trace.update({"title": event.agent_role, "strategy_key": event.strategy_key})
            self._emit(
                render.render_scenario_card(
                    {
                        "scope": "agent",
                        "agent_role": event.agent_role,
                        "strategy_key": event.strategy_key,
                        "from_role": event.from_role,
                        "objective_preview": event.objective_preview,
                    }
                )
            )

    def _on_agent_run_finished(self, stamped: StampedEvent, event: AgentRunFinished) -> None:
        state = self._state_of(stamped)
        run = state.runs.get(stamped.scope.run_id, {})
        run.update({"status": event.status, "steps": event.steps, "error": event.error})
        start = run.get("start_ts")
        if start is not None:
            run["duration_s"] = stamped.ts - start
        if not state.is_team and not stamped.scope.parent_run_id:
            state.trace.update({"status": event.status, "steps": event.steps})
            self._finish_trace(stamped, state, error=event.error)

    def _finish_trace(self, stamped: StampedEvent, state: _TraceState, *, error: str) -> None:
        trace = state.trace
        started = next((s.ts for s in state.events), stamped.ts)
        trace["duration_s"] = stamped.ts - started
        if error:
            trace["error"] = error
        runs = [r for r in state.runs.values() if r.get("role") not in (None, "(team)")]
        trace["runs"] = runs
        trace["llm_calls"] = sum(r.get("llm_calls", 0) for r in runs)
        trace["tokens_in"] = sum(r.get("tokens_in", 0) for r in runs)
        trace["tokens_out"] = sum(r.get("tokens_out", 0) for r in runs)
        trace["tool_calls"] = sum(r.get("tool_calls", 0) for r in runs)
        self._emit(render.render_run_card(trace))
        if self._verbosity is Verbosity.VERBOSE:
            diagram = render_sequence_diagram(state.events)
            if diagram:
                self._emit("\n" + diagram)
        self._traces.pop(stamped.scope.trace_id, None)

    # ── 叙事行（standard+）─────────────────────────────
    def _on_narrative_event(self, stamped: StampedEvent, event: JournalEvent) -> None:
        if self._verbosity is Verbosity.MINIMAL:
            return
        line = self._narrative_line(stamped, event)
        if not line:
            return
        state = self._state_of(stamped)
        role = stamped.scope.agent_role
        if role and role != state.last_section:
            self._emit(render.section_header(role))
            state.last_section = role
        self._emit("  " + line)

    def _narrative_line(self, stamped: StampedEvent, event: JournalEvent) -> str:
        renderer = self._narrative_renderers.get(type(event))
        if renderer is not None:
            return renderer(stamped, event)
        return ""

    # ── 叙事行渲染方法 ────────────────────────────────
    def _render_delegation_issued(self, stamped: StampedEvent, event: DelegationIssued) -> str:
        # 增量投影：将委派事件加入索引，后续查找 O(1)
        state = self._state_of(stamped)
        state.delegation_issued[event.delegation_id] = stamped
        return f"⇢ {event.callee_role}: {event.subtask_preview}"

    def _render_delegation_completed(
        self, stamped: StampedEvent, event: DelegationCompleted
    ) -> str:
        callee = self._delegation_callee(stamped, event.delegation_id)
        duration = self._delegation_duration(stamped, event.delegation_id)
        suffix = f" · {duration:.1f}s" if duration is not None else ""
        return f"⇠ {callee} {event.status}{suffix}"

    def _render_delegation_cache_hit(self, stamped: StampedEvent, event: DelegationCacheHit) -> str:
        return f"⇢ {event.callee_role}: 幂等短路（复用已返回结果）"

    def _render_llm_completed(self, stamped: StampedEvent, event: LlmCallCompleted) -> str:
        self._observe_llm(stamped, event)
        tokens = (
            f" · tokens {event.prompt_tokens}/{event.completion_tokens}"
            if event.prompt_tokens or event.completion_tokens
            else ""
        )
        line = f"llm.chat {event.model} · {event.latency_ms}ms{tokens}"
        if self._verbosity is Verbosity.VERBOSE and event.prompt_preview:
            line += (
                f"\n    ┌ prompt: {event.prompt_preview}\n    └ response: {event.response_preview}"
            )
        return line if event.ok else f"{line} · FAIL"

    def _render_tool_invoked(self, stamped: StampedEvent, event: ToolInvoked) -> str:
        self._observe_tool(stamped)
        mark = "ok" if event.ok else "FAIL"
        return f"tool {event.tool_name} · {mark} · {event.latency_ms}ms"

    def _render_tool_denied(self, stamped: StampedEvent, event: ToolDenied) -> str:
        return f"⛔ tool denied: {event.tool_name} ({event.reason})"

    def _render_decision_made(self, stamped: StampedEvent, event: DecisionMade) -> str:
        target = f" → {event.delegate_target}" if event.delegate_target else ""
        return f"decision: {event.action_type}{target}"

    def _render_synthesis_completed(self, stamped: StampedEvent, event: SynthesisCompleted) -> str:
        run = self._state_of(stamped).runs.get(stamped.scope.run_id)
        if run is not None:
            run["synthesis_candidates"] = event.candidate_count
        return f"◈ synthesis ({event.method}, {event.candidate_count} candidates)"

    def _render_action_degraded(self, stamped: StampedEvent, event: ActionDegraded) -> str:
        return f"⚠ degraded: {event.original_action_type} → {event.degraded_to}"

    def _render_casting_started(self, stamped: StampedEvent, event: CastingStarted) -> str:
        return f"◎ 自动选角 · {event.objective_preview}"

    def _render_casting_completed(self, stamped: StampedEvent, event: CastingCompleted) -> str:
        roles = "、".join(event.selected_roles)
        lead = f" · 主导 {event.lead_role}" if event.lead_role else ""
        return f"✓ 组队完成 · {event.governance_kind}{lead} · {roles}"

    def _render_casting_failed(self, stamped: StampedEvent, event: CastingFailed) -> str:
        return f"✗ 组队失败 · {event.error}"

    # ── 聚合与工具 ─────────────────────────────────────
    def _observe_llm(self, stamped: StampedEvent, event: LlmCallCompleted) -> None:
        run = self._state_of(stamped).runs.setdefault(stamped.scope.run_id, {})
        run["llm_calls"] = run.get("llm_calls", 0) + 1
        run["tokens_in"] = run.get("tokens_in", 0) + event.prompt_tokens
        run["tokens_out"] = run.get("tokens_out", 0) + event.completion_tokens

    def _observe_tool(self, stamped: StampedEvent) -> None:
        run = self._state_of(stamped).runs.setdefault(stamped.scope.run_id, {})
        run["tool_calls"] = run.get("tool_calls", 0) + 1

    def _delegation_duration(self, stamped: StampedEvent, delegation_id: str) -> float | None:
        # 增量投影：使用索引查找，O(1) 替代 O(n) 线性扫描
        state = self._state_of(stamped)
        issued_stamped = state.delegation_issued.get(delegation_id)
        if issued_stamped is not None:
            return stamped.ts - issued_stamped.ts
        return None

    def _delegation_callee(self, stamped: StampedEvent, delegation_id: str) -> str:
        # 增量投影：使用索引查找，O(1) 替代 O(n) 线性扫描
        state = self._state_of(stamped)
        issued_stamped = state.delegation_issued.get(delegation_id)
        if issued_stamped is not None:
            event = issued_stamped.event
            if isinstance(event, DelegationIssued):
                return event.callee_role
        return ""

    def _state_of(self, stamped: StampedEvent) -> _TraceState:
        trace_id = stamped.scope.trace_id or "(unknown)"
        state = self._traces.get(trace_id)
        if state is None:
            if len(self._traces) >= _MAX_BUFFERED_TRACES:
                self._traces.pop(next(iter(self._traces)))
            state = _TraceState()
            self._traces[trace_id] = state
        return state

    def _emit(self, text: str) -> None:
        print(text, file=self._stream, flush=True)
