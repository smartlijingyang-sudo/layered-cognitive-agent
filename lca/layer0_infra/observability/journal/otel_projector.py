"""OtelProjector —— journal → OTel span 投影的状态机（ADR-0037）。

原则：**拓扑由关联骨架显式生成，不再依赖 ambient context 继承**。
- 容器 span（run.team / run.agent / delegation）在 Started/Issued 事件打开、
  Finished/Completed 事件关闭，句柄按 run_id / delegation_id 索引；
- 子 span 的父节点经 ``RunScope`` 的 delegation_id / parent_run_id / run_id
  显式查表（``start_span(context=...)``）——0 秒化石 span 与错挂父子链
  在构造上不可能；
- 资源事实（Llm/Tool）以事件自带 ts + latency_ms 还原显式起止时间；
- 瞬时事实投影为所属 run span 的 OTel event，不再是孤儿 0 秒 span。

属性映射（含 Langfuse/gen_ai 约定）在 ``otel_mapping`` 纯函数层；
泄漏容器（run 未正常关闭）在 close 时兜底收尾。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

import structlog
from opentelemetry import trace as otel_trace

from lca.contracts.journal import (
    ActionDegraded,
    AgentRunFinished,
    AgentRunStarted,
    DecisionMade,
    DelegationCacheHit,
    DelegationCompleted,
    DelegationIssued,
    JournalEvent,
    LlmCallCompleted,
    RunInsight,
    RunScope,
    StampedEvent,
    StepCompleted,
    SynthesisCompleted,
    TeamRunFinished,
    TeamRunStarted,
    ToolDenied,
    ToolInvoked,
)
from lca.contracts.protocols import JournalProjector
from lca.contracts.telemetry import EventName, SpanName
from lca.layer0_infra.observability.journal import otel_genai_mapping as genai
from lca.layer0_infra.observability.journal import otel_mapping as mapping

if TYPE_CHECKING:
    from opentelemetry.trace import Span, Tracer

_log = structlog.get_logger("lca.journal.otel")

_NANOS_PER_SECOND = 1_000_000_000
_NANOS_PER_MILLI = 1_000_000

EventHandler = Callable[[StampedEvent], None]


def _nanos(ts_seconds: float) -> int:
    return int(ts_seconds * _NANOS_PER_SECOND)


class OtelProjector(JournalProjector):
    """journal 事件 → OTel span/event：显式父子、显式起止。"""

    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer
        self._open_runs: dict[str, Span] = {}
        self._open_delegations: dict[str, Span] = {}
        self._handlers: dict[type[JournalEvent], EventHandler] = {
            TeamRunStarted: self._on_team_run_started,
            TeamRunFinished: self._on_team_run_finished,
            AgentRunStarted: self._on_agent_run_started,
            AgentRunFinished: self._on_agent_run_finished,
            DelegationIssued: self._on_delegation_issued,
            DelegationCompleted: self._on_delegation_completed,
            LlmCallCompleted: self._on_llm_call_completed,
            ToolInvoked: self._on_tool_invoked,
            DecisionMade: self._on_decision_made,
            StepCompleted: self._on_step_completed,
            ActionDegraded: self._on_action_degraded,
            ToolDenied: self._on_tool_denied,
            DelegationCacheHit: self._on_delegation_cache_hit,
            SynthesisCompleted: self._on_synthesis_completed,
            RunInsight: self._on_run_insight,
        }

    # ── JournalProjector ───────────────────────────────
    def on_event(self, stamped: StampedEvent) -> None:
        handler = self._handlers.get(type(stamped.event))
        if handler is not None:
            handler(stamped)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        for span in self._drain_leaked():
            _log.warning("journal_otel_container_leaked")
            span.end()

    # ── 父节点解析（关联骨架 → 显式 context）──────────
    def _spawner_span(self, scope: RunScope) -> Span | None:
        """容器开启者的父 span：优先生成它的委派，其次生成它的 run。"""
        if scope.delegation_id:
            span = self._open_delegations.get(scope.delegation_id)
            if span is not None:
                return span
        if scope.parent_run_id:
            return self._open_runs.get(scope.parent_run_id)
        return None

    def _run_span(self, scope: RunScope) -> Span | None:
        """当前 run 的 span（run 内事件/子委派的父节点）。"""
        return self._open_runs.get(scope.run_id)

    def _context_of(self, span: Span | None) -> Any:
        return otel_trace.set_span_in_context(span) if span is not None else None

    def _start(
        self,
        name: str,
        parent: Span | None,
        attributes: dict[str, Any],
        *,
        start_nanos: int | None = None,
    ) -> Span:
        return self._tracer.start_span(
            name, attributes=attributes, context=self._context_of(parent), start_time=start_nanos
        )

    def _start_nanos(self, stamped: StampedEvent, latency_ms: int) -> int:
        return _nanos(stamped.ts) - latency_ms * _NANOS_PER_MILLI

    # ── 容器事件 ───────────────────────────────────────
    def _on_team_run_started(self, stamped: StampedEvent) -> None:
        span = self._start(
            SpanName.RUN_TEAM.value,
            None,
            mapping.team_run_started_attrs(cast("TeamRunStarted", stamped.event)),
            start_nanos=_nanos(stamped.ts),
        )
        self._open_runs[stamped.scope.run_id] = span

    def _on_team_run_finished(self, stamped: StampedEvent) -> None:
        span = self._open_runs.pop(stamped.scope.run_id, None)
        if span is None:
            return
        span.set_attributes(mapping.team_run_finished_attrs(cast("TeamRunFinished", stamped.event)))
        span.end(end_time=_nanos(stamped.ts))

    def _on_agent_run_started(self, stamped: StampedEvent) -> None:
        span = self._start(
            SpanName.RUN_AGENT.value,
            self._spawner_span(stamped.scope),
            mapping.agent_run_started_attrs(cast("AgentRunStarted", stamped.event)),
            start_nanos=_nanos(stamped.ts),
        )
        self._open_runs[stamped.scope.run_id] = span

    def _on_agent_run_finished(self, stamped: StampedEvent) -> None:
        span = self._open_runs.pop(stamped.scope.run_id, None)
        if span is None:
            return
        span.set_attributes(
            mapping.agent_run_finished_attrs(cast("AgentRunFinished", stamped.event))
        )
        span.end(end_time=_nanos(stamped.ts))

    # ── 委派（一等公民）────────────────────────────────
    def _on_delegation_issued(self, stamped: StampedEvent) -> None:
        event = cast("DelegationIssued", stamped.event)
        span = self._start(
            SpanName.DELEGATION.value,
            self._run_span(stamped.scope),
            mapping.delegation_issued_attrs(event),
            start_nanos=_nanos(stamped.ts),
        )
        self._open_delegations[event.delegation_id] = span

    def _on_delegation_completed(self, stamped: StampedEvent) -> None:
        event = cast("DelegationCompleted", stamped.event)
        span = self._open_delegations.pop(event.delegation_id, None)
        if span is None:
            return
        span.set_attributes(mapping.delegation_completed_attrs(event))
        span.end(end_time=_nanos(stamped.ts))

    # ── 资源事实（显式起止时间）────────────────────────
    def _on_llm_call_completed(self, stamped: StampedEvent) -> None:
        event = cast("LlmCallCompleted", stamped.event)
        span = self._start(
            SpanName.LLM_CHAT.value,
            self._run_span(stamped.scope),
            genai.llm_call_attrs(event),
            start_nanos=self._start_nanos(stamped, event.latency_ms),
        )
        span.end(end_time=_nanos(stamped.ts))

    def _on_tool_invoked(self, stamped: StampedEvent) -> None:
        event = cast("ToolInvoked", stamped.event)
        span = self._start(
            SpanName.TOOL_EXECUTE.value,
            self._run_span(stamped.scope),
            mapping.tool_invoked_attrs(event),
            start_nanos=self._start_nanos(stamped, event.latency_ms),
        )
        span.end(end_time=_nanos(stamped.ts))

    # ── 瞬时事实（投影为所属 run span 的 event）────
    def _add_run_event(self, stamped: StampedEvent, name: str, attributes: dict[str, Any]) -> None:
        span = self._run_span(stamped.scope)
        if span is None:
            return
        span.add_event(name, attributes)

    def _on_decision_made(self, stamped: StampedEvent) -> None:
        self._add_run_event(
            stamped,
            EventName.DECISION_MADE.value,
            mapping.decision_made_attrs(cast("DecisionMade", stamped.event)),
        )

    def _on_step_completed(self, stamped: StampedEvent) -> None:
        self._add_run_event(
            stamped,
            EventName.STEP_COMPLETED.value,
            mapping.step_completed_attrs(cast("StepCompleted", stamped.event)),
        )

    def _on_action_degraded(self, stamped: StampedEvent) -> None:
        self._add_run_event(
            stamped,
            EventName.ACTION_DEGRADED.value,
            mapping.action_degraded_attrs(cast("ActionDegraded", stamped.event)),
        )

    def _on_tool_denied(self, stamped: StampedEvent) -> None:
        self._add_run_event(
            stamped,
            EventName.TOOL_DENIED.value,
            mapping.tool_denied_attrs(cast("ToolDenied", stamped.event)),
        )

    def _on_delegation_cache_hit(self, stamped: StampedEvent) -> None:
        self._add_run_event(
            stamped,
            SpanName.DELEGATE_CACHE_HIT.value,
            mapping.delegation_cache_hit_attrs(cast("DelegationCacheHit", stamped.event)),
        )

    def _on_synthesis_completed(self, stamped: StampedEvent) -> None:
        self._add_run_event(
            stamped,
            SpanName.TEAM_SYNTHESIS.value,
            mapping.synthesis_completed_attrs(cast("SynthesisCompleted", stamped.event)),
        )

    def _on_run_insight(self, stamped: StampedEvent) -> None:
        self._add_run_event(
            stamped,
            EventName.RUN_INSIGHT.value,
            mapping.run_insight_attrs(cast("RunInsight", stamped.event)),
        )

    # ── 泄漏兜底 ───────────────────────────────────────
    def _drain_leaked(self) -> list[Span]:
        leaked = [*self._open_runs.values(), *self._open_delegations.values()]
        self._open_runs.clear()
        self._open_delegations.clear()
        return leaked
