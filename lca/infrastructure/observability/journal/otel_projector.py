"""OtelProjector —— journal → OTel span 投影的语义分派器（ADR-0037）。

两条正交的父子机制，各司其职：
1. **投影器自己的 span（run/delegation/llm/tool）用关联骨架显式定父**
   （``start_span(context=set_span_in_context(parent))``）——与事件到达顺序
   无关，并行委派的多个成员各挂各的 delegation，绝不串线；0 秒化石 span 与
   错挂父子链构造上不可能。
2. **run 容器额外 attach 进 ambient**——机制平面 span（loop.phase/memory/
   transport，仍走旧 ``span()`` API）以 run.agent 为最近附着祖先，正确归位。
   delegation 不 attach（并行会互相覆盖），其子 run.agent 靠关联 id 定父。

- 资源事实（Llm/Tool）以事件自带 ts + latency_ms 还原显式起止时间；
- 瞬时事实投影为 EVENT 观测（自托管 Langfuse 不导出 OTel span event，
  以 ``langfuse.observation.type=event`` 零时长 span 承载）；
  step.completed 是生命周期噪音，只留在 journal，不进 Langfuse；
- 容器生命周期委托 ``SpanContainerIndex``；泄漏容器 close 时兜底收尾。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

import structlog
from opentelemetry import trace as otel_trace

if TYPE_CHECKING:
    from lca.infrastructure.observability.genai.registry import GenAISemanticMapperRegistry

from lca.contracts.atoms.telemetry import (
    ATTR_AGENT_ROLE,
    ATTR_RATIONALE_PREVIEW,
    ATTR_SUMMARY,
    EventName,
    SpanName,
)
from lca.contracts.models.observability.journal import (
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
from lca.infrastructure.observability.event_catalog import may_export_externally
from lca.infrastructure.observability.journal import otel_genai_mapping as genai
from lca.infrastructure.observability.journal import otel_mapping as mapping
from lca.infrastructure.observability.journal.otel_mapping import EVENT_PROJECTIONS
from lca.infrastructure.observability.journal.otel_span_index import SpanContainerIndex
from lca.infrastructure.observability.langfuse_conventions import (
    LANGFUSE_OBSERVATION_INPUT,
    LANGFUSE_OBSERVATION_TYPE,
    OBSERVATION_TYPE_EVENT,
)

if TYPE_CHECKING:
    from opentelemetry.trace import Span, Tracer

_log = structlog.get_logger("lca.journal.otel")

_NANOS_PER_SECOND = 1_000_000_000
_NANOS_PER_MILLI = 1_000_000

_EVENT_INPUT_MAX = 3
"""EVENT 观测 input 缺失时，用前 N 个属性拼摘要。"""


def _nanos(ts_seconds: float) -> int:
    return int(ts_seconds * _NANOS_PER_SECOND)


def _event_input(attributes: dict[str, Any]) -> str:
    """EVENT 观测的人类可读 input：优先 rationale/summary，否则属性摘要。"""
    for key in (ATTR_RATIONALE_PREVIEW, ATTR_SUMMARY):
        value = attributes.get(key)
        if value:
            return str(value)
    items = [f"{k}={v}" for k, v in list(attributes.items())[:_EVENT_INPUT_MAX]]
    return " ".join(items)


class OtelProjector(JournalProjector):
    """journal 事件 → OTel span/观测：显式定父、run 容器 attach、显式起止。"""

    def __init__(
        self,
        tracer: Tracer,
        *,
        genai_mapper_registry: GenAISemanticMapperRegistry | None = None,
    ) -> None:
        self._index = SpanContainerIndex(tracer)
        self._tracer = tracer
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
        self._genai_registry = genai_mapper_registry

    # ── JournalProjector ───────────────────────────────
    def on_event(self, stamped: StampedEvent) -> None:
        if not may_export_externally(stamped.event):
            return
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
        for span in self._index.drain_leaked():
            _log.warning("journal_otel_container_leaked")
            span.end()

    # ── 父节点解析（关联骨架 → 显式 context）──────────
    def _spawner_span(self, scope: RunScope) -> Span | None:
        """容器开启者的父 span：优先生成它的委派，其次生成它的 run。"""
        if scope.delegation_id:
            span = self._index.delegation_span(scope.delegation_id)
            if span is not None:
                return span
        if scope.parent_run_id:
            return self._index.run_span(scope.parent_run_id)
        return None

    def _delegation_parent(self, scope: RunScope) -> Span | None:
        """委派父节点：策略层包络（如 team.round，非投影器产物）就近取 ambient，
        否则退回关联骨架（run_id）。并行委派各挂各的父，绝不串线。"""
        ambient = otel_trace.get_current_span()
        if ambient.is_recording() and not self._index.is_own_span(ambient):
            return ambient
        return self._index.run_span(scope.run_id)

    @staticmethod
    def _start_nanos(stamped: StampedEvent, latency_ms: int) -> int:
        return _nanos(stamped.ts) - latency_ms * _NANOS_PER_MILLI

    # ── 容器事件 ───────────────────────────────────────
    def _on_team_run_started(self, stamped: StampedEvent) -> None:
        self._index.start(
            stamped.scope.run_id,
            SpanName.RUN_TEAM.value,
            None,
            mapping.team_run_started_attrs(cast("TeamRunStarted", stamped.event)),
            start_nanos=_nanos(stamped.ts),
            is_run=True,
            attach=True,
        )

    def _on_team_run_finished(self, stamped: StampedEvent) -> None:
        self._index.end(
            stamped.scope.run_id,
            mapping.team_run_finished_attrs(cast("TeamRunFinished", stamped.event)),
            end_nanos=_nanos(stamped.ts),
        )

    def _on_agent_run_started(self, stamped: StampedEvent) -> None:
        self._index.start(
            stamped.scope.run_id,
            SpanName.RUN_AGENT.value,
            self._spawner_span(stamped.scope),
            mapping.agent_run_started_attrs(cast("AgentRunStarted", stamped.event)),
            start_nanos=_nanos(stamped.ts),
            is_run=True,
            attach=True,
        )

    def _on_agent_run_finished(self, stamped: StampedEvent) -> None:
        self._index.end(
            stamped.scope.run_id,
            mapping.agent_run_finished_attrs(cast("AgentRunFinished", stamped.event)),
            end_nanos=_nanos(stamped.ts),
        )

    # ── 委派（一等公民，显式定父、不 attach）────────────
    def _on_delegation_issued(self, stamped: StampedEvent) -> None:
        event = cast("DelegationIssued", stamped.event)
        mechanism = getattr(event.mechanism, "value", event.mechanism)
        if mechanism == DelegationMechanism.HANDOFF.value:
            # 非阻塞移交无回执：投影为 EVENT 观测，不开容器（无泄漏）
            self._project_run_event(
                stamped, EventName.DELEGATE_REQUESTED.value, mapping.delegation_issued_attrs(event)
            )
            return
        self._index.start(
            event.delegation_id,
            SpanName.DELEGATION.value,
            self._delegation_parent(stamped.scope),
            mapping.delegation_issued_attrs(event),
            start_nanos=_nanos(stamped.ts),
            is_run=False,
        )

    def _on_delegation_completed(self, stamped: StampedEvent) -> None:
        event = cast("DelegationCompleted", stamped.event)
        self._index.end(
            event.delegation_id,
            mapping.delegation_completed_attrs(event),
            end_nanos=_nanos(stamped.ts),
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
            context=self._index.context_of(self._index.run_span(stamped.scope.run_id)),
            start_time=self._start_nanos(stamped, latency_ms),
        )
        span.end(end_time=_nanos(stamped.ts))

    def _on_llm_call_completed(self, stamped: StampedEvent) -> None:
        event = cast("LlmCallCompleted", stamped.event)
        base = genai.llm_call_attrs(event)
        merged = self._merge_genai(stamped, base)
        self._emit_timed_span(stamped, SpanName.LLM_CHAT.value, merged, event.latency_ms)

    def _on_tool_invoked(self, stamped: StampedEvent) -> None:
        event = cast("ToolInvoked", stamped.event)
        base = mapping.tool_invoked_attrs(event)
        merged = self._merge_genai(stamped, base)
        self._emit_timed_span(
            stamped,
            SpanName.TOOL_EXECUTE.value,
            merged,
            event.latency_ms,
        )

    def _merge_genai(self, stamped: StampedEvent, base: dict[str, Any]) -> dict[str, Any]:
        """若配了 genai_mapper_registry，把 mapper 产生的属性并入基础属性。"""
        if self._genai_registry is None:
            return base
        mapper = self._genai_registry.for_event(stamped)
        if mapper is None:
            return base
        merged = dict(base)
        merged.update(mapper.map(stamped))
        return merged

    # ── 瞬时事实（投影为 EVENT 观测）────────────────────
    def _project_run_event(
        self, stamped: StampedEvent, name: str, attributes: dict[str, Any]
    ) -> None:
        if name == EventName.STEP_COMPLETED.value:
            return
        attrs = dict(attributes)
        attrs[LANGFUSE_OBSERVATION_TYPE] = OBSERVATION_TYPE_EVENT
        summary = _event_input(attrs)
        if summary:
            attrs[LANGFUSE_OBSERVATION_INPUT] = summary
        span = self._tracer.start_span(
            name,
            attributes=attrs,
            context=self._index.context_of(self._index.run_span(stamped.scope.run_id)),
            start_time=_nanos(stamped.ts),
        )
        span.end(end_time=_nanos(stamped.ts))
