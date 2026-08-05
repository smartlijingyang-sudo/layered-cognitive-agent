"""OtelProjector —— journal → OTel span 投影的状态机（ADR-0037）。

两条正交的父子机制，各司其职：
1. **投影器自己的 span（run/delegation/llm/tool）用关联骨架显式定父**
   （``start_span(context=set_span_in_context(parent))``）——与事件到达顺序
   无关，并行委派的多个成员各挂各的 delegation，绝不串线；0 秒化石 span 与
   错挂父子链构造上不可能。
2. **run 容器额外 attach 进 ambient**——机制平面 span（loop.phase/memory/
   transport，仍走旧 ``span()`` API）以 run.agent 为最近附着祖先，正确归位。
   delegation 不 attach（并行会互相覆盖），其子 run.agent 靠关联 id 定父。

- 资源事实（Llm/Tool）以事件自带 ts + latency_ms 还原显式起止时间；
- 瞬时事实按投影表统一落为所属 run span 的 OTel event（非孤儿 0 秒 span）；
- 泄漏容器（run 未正常关闭）在 close 时兜底收尾（含 detach）。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

import structlog
from opentelemetry import context as otel_context
from opentelemetry import trace as otel_trace

from lca.contracts.journal import (
    AgentRunFinished,
    AgentRunStarted,
    DelegationCompleted,
    DelegationIssued,
    DelegationMechanism,
    JournalEvent,
    LlmCallCompleted,
    RunScope,
    StampedEvent,
    TeamRunFinished,
    TeamRunStarted,
    ToolInvoked,
)
from lca.contracts.protocols import JournalProjector
from lca.contracts.telemetry import ATTR_AGENT_ROLE, EventName, SpanName
from lca.layer0_infra.observability.journal import otel_genai_mapping as genai
from lca.layer0_infra.observability.journal import otel_mapping as mapping
from lca.layer0_infra.observability.journal.otel_mapping import EVENT_PROJECTIONS

if TYPE_CHECKING:
    from opentelemetry.context import Token
    from opentelemetry.trace import Span, Tracer

_log = structlog.get_logger("lca.journal.otel")

_NANOS_PER_SECOND = 1_000_000_000
_NANOS_PER_MILLI = 1_000_000


def _nanos(ts_seconds: float) -> int:
    return int(ts_seconds * _NANOS_PER_SECOND)


class OtelProjector(JournalProjector):
    """journal 事件 → OTel span/event：显式定父、run 容器 attach、显式起止。"""

    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer
        self._open_runs: dict[str, Span] = {}
        self._open_delegations: dict[str, Span] = {}
        self._attach_tokens: dict[str, Token] = {}
        self._own_span_ids: set[str] = set()
        self._handlers: dict[type[JournalEvent], Callable[[StampedEvent], None]] = {
            TeamRunStarted: self._on_team_run_started,
            TeamRunFinished: self._on_team_run_finished,
            AgentRunStarted: self._on_agent_run_started,
            AgentRunFinished: self._on_agent_run_finished,
            DelegationIssued: self._on_delegation_issued,
            DelegationCompleted: self._on_delegation_completed,
            LlmCallCompleted: self._on_llm_call_completed,
            ToolInvoked: self._on_tool_invoked,
        }

    # ── JournalProjector ───────────────────────────────
    def on_event(self, stamped: StampedEvent) -> None:
        handler = self._handlers.get(type(stamped.event))
        if handler is not None:
            handler(stamped)
            return
        projection = EVENT_PROJECTIONS.get(type(stamped.event))
        if projection is not None:
            self._project_run_event(stamped, projection[0], projection[1](stamped.event))

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
        """当前 run 的 span（run 内资源/委派/事件的父节点）。"""
        return self._open_runs.get(scope.run_id)

    def _context_of(self, span: Span | None) -> Any:
        return otel_trace.set_span_in_context(span) if span is not None else None

    def _start(
        self,
        name: str,
        parent: Span | None,
        attributes: dict[str, Any],
        *,
        start_nanos: int,
        attach_key: str | None = None,
    ) -> Span:
        """start_span 显式定父；``attach_key`` 非空时同时 attach 进 ambient。"""
        span = self._tracer.start_span(
            name, attributes=attributes, context=self._context_of(parent), start_time=start_nanos
        )
        self._own_span_ids.add(format(span.get_span_context().span_id, "016x"))
        if attach_key is not None:
            self._attach_tokens[attach_key] = otel_context.attach(
                otel_trace.set_span_in_context(span)
            )
        return span

    def _forget_span(self, span: Span) -> None:
        self._own_span_ids.discard(format(span.get_span_context().span_id, "016x"))

    def _end_container(
        self,
        key: str,
        open_map: dict[str, Span],
        attributes: dict[str, Any],
        *,
        end_nanos: int,
        detach: bool,
    ) -> None:
        span = open_map.pop(key, None)
        if span is None:
            return
        span.set_attributes(attributes)
        span.end(end_time=end_nanos)
        self._forget_span(span)
        if detach:
            token = self._attach_tokens.pop(key, None)
            if token is not None:
                otel_context.detach(token)

    def _start_nanos(self, stamped: StampedEvent, latency_ms: int) -> int:
        return _nanos(stamped.ts) - latency_ms * _NANOS_PER_MILLI

    def _delegation_parent(self, scope: RunScope) -> Span | None:
        """委派父节点：策略层包络（如 team.round，非投影器产物）就近取 ambient，
        否则退回关联骨架（run_id）。并行委派各挂各的父，绝不串线。"""
        ambient = otel_trace.get_current_span()
        if ambient.is_recording():
            ambient_id = format(ambient.get_span_context().span_id, "016x")
            if ambient_id not in self._own_span_ids:
                return ambient
        return self._run_span(scope)

    # ── 容器事件 ───────────────────────────────────────
    def _on_team_run_started(self, stamped: StampedEvent) -> None:
        span = self._start(
            SpanName.RUN_TEAM.value,
            None,
            mapping.team_run_started_attrs(cast("TeamRunStarted", stamped.event)),
            start_nanos=_nanos(stamped.ts),
            attach_key=stamped.scope.run_id,
        )
        self._open_runs[stamped.scope.run_id] = span

    def _on_team_run_finished(self, stamped: StampedEvent) -> None:
        self._end_container(
            stamped.scope.run_id,
            self._open_runs,
            mapping.team_run_finished_attrs(cast("TeamRunFinished", stamped.event)),
            end_nanos=_nanos(stamped.ts),
            detach=True,
        )

    def _on_agent_run_started(self, stamped: StampedEvent) -> None:
        span = self._start(
            SpanName.RUN_AGENT.value,
            self._spawner_span(stamped.scope),
            mapping.agent_run_started_attrs(cast("AgentRunStarted", stamped.event)),
            start_nanos=_nanos(stamped.ts),
            attach_key=stamped.scope.run_id,
        )
        self._open_runs[stamped.scope.run_id] = span

    def _on_agent_run_finished(self, stamped: StampedEvent) -> None:
        self._end_container(
            stamped.scope.run_id,
            self._open_runs,
            mapping.agent_run_finished_attrs(cast("AgentRunFinished", stamped.event)),
            end_nanos=_nanos(stamped.ts),
            detach=True,
        )

    # ── 委派（一等公民，显式定父、不 attach）────────────
    def _on_delegation_issued(self, stamped: StampedEvent) -> None:
        event = cast("DelegationIssued", stamped.event)
        mechanism = getattr(event.mechanism, "value", event.mechanism)
        if mechanism == DelegationMechanism.HANDOFF.value:
            # 非阻塞移交无回执：投影为 run span 事件，不开容器（无泄漏）
            self._project_run_event(
                stamped, EventName.DELEGATE_REQUESTED.value, mapping.delegation_issued_attrs(event)
            )
            return
        span = self._start(
            SpanName.DELEGATION.value,
            self._delegation_parent(stamped.scope),
            mapping.delegation_issued_attrs(event),
            start_nanos=_nanos(stamped.ts),
        )
        self._open_delegations[event.delegation_id] = span

    def _on_delegation_completed(self, stamped: StampedEvent) -> None:
        event = cast("DelegationCompleted", stamped.event)
        self._end_container(
            event.delegation_id,
            self._open_delegations,
            mapping.delegation_completed_attrs(event),
            end_nanos=_nanos(stamped.ts),
            detach=False,
        )

    # ── 资源事实（显式起止、显式定父）──────────────────
    def _emit_timed_span(
        self, stamped: StampedEvent, name: str, attributes: dict[str, Any], latency_ms: int
    ) -> None:
        attrs = dict(attributes)
        if stamped.scope.agent_role:
            attrs.setdefault(ATTR_AGENT_ROLE, stamped.scope.agent_role)
        span = self._tracer.start_span(
            name,
            attributes=attrs,
            context=self._context_of(self._run_span(stamped.scope)),
            start_time=self._start_nanos(stamped, latency_ms),
        )
        span.end(end_time=_nanos(stamped.ts))

    def _on_llm_call_completed(self, stamped: StampedEvent) -> None:
        event = cast("LlmCallCompleted", stamped.event)
        self._emit_timed_span(
            stamped, SpanName.LLM_CHAT.value, genai.llm_call_attrs(event), event.latency_ms
        )

    def _on_tool_invoked(self, stamped: StampedEvent) -> None:
        event = cast("ToolInvoked", stamped.event)
        self._emit_timed_span(
            stamped,
            SpanName.TOOL_EXECUTE.value,
            mapping.tool_invoked_attrs(event),
            event.latency_ms,
        )

    # ── 瞬时事实（投影为所属 run span 的 event）────
    def _project_run_event(
        self, stamped: StampedEvent, name: str, attributes: dict[str, Any]
    ) -> None:
        span = self._run_span(stamped.scope)
        if span is None:
            return
        span.add_event(name, attributes)

    # ── 泄漏兜底 ───────────────────────────────────────
    def _drain_leaked(self) -> list[Span]:
        leaked = [*self._open_runs.values(), *self._open_delegations.values()]
        for key in (*self._open_runs, *self._open_delegations):
            token = self._attach_tokens.pop(key, None)
            if token is not None:
                otel_context.detach(token)
        for span in leaked:
            self._forget_span(span)
        self._open_runs.clear()
        self._open_delegations.clear()
        return leaked
