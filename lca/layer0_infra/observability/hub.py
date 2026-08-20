"""运行可观测性组合根。

``ObservabilityHub`` 装配一个事件账本、零到多个只读投影和外部 OTel 导出器。
它不维护第二条诊断流：插件与运行边界的解释记录也作为 ``RuntimeObserved``
提交到同一账本，再由需要的 JSONL、控制台、SSE 或 OTel 投影消费。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

import structlog
from opentelemetry import trace as otel_trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBased, TraceIdRatioBased

from lca.contracts.atoms.telemetry import ATTR_AGENT_ROLE, ATTR_STEP
from lca.contracts.models.observability.diagnostic import (
    DiagnosticCategory,
    DiagnosticStatus,
)
from lca.contracts.models.observability.event import OperationOutcome, RuntimeKind
from lca.contracts.models.observability.journal import RuntimeObserved, StampedEvent
from lca.contracts.protocols import DiagnosticSink, JournalProjector, ObservabilityBackend
from lca.layer0_infra.observability.handles import SpanHandle, _IsolatedExporter
from lca.layer0_infra.observability.journal.engine import RunStore
from lca.layer0_infra.observability.journal.otel_projector import OtelProjector
from lca.layer0_infra.observability.langfuse_conventions import LANGFUSE_ENVIRONMENT
from lca.layer0_infra.observability.policy import AttributePolicy
from lca.layer0_infra.observability.projection_registry import ProjectionRegistry
from lca.layer0_infra.observability.run_diagnostics import DiagnosticJsonlProjection

_log = structlog.get_logger("lca.observability")

_TRACER_NAME = "lca"
_SERVICE_NAME_KEY = "service.name"
_DEFAULT_SERVICE_NAME = "lca"

_KIND_BY_CATEGORY: dict[DiagnosticCategory, RuntimeKind] = {
    DiagnosticCategory.AGENT: RuntimeKind.AGENT,
    DiagnosticCategory.PLUGIN: RuntimeKind.PLUGIN,
    DiagnosticCategory.HOOK: RuntimeKind.HOOK,
    DiagnosticCategory.LLM: RuntimeKind.LLM,
    DiagnosticCategory.TOOL: RuntimeKind.TOOL,
    DiagnosticCategory.MEMORY: RuntimeKind.MEMORY,
    DiagnosticCategory.TRANSPORT: RuntimeKind.TRANSPORT,
    DiagnosticCategory.INFRA: RuntimeKind.PLUGIN,
    DiagnosticCategory.JOURNAL: RuntimeKind.PLUGIN,
}

_OUTCOME_BY_STATUS: dict[DiagnosticStatus, OperationOutcome] = {
    DiagnosticStatus.INFO: OperationOutcome.OK,
    DiagnosticStatus.STARTED: OperationOutcome.STARTED,
    DiagnosticStatus.SUCCEEDED: OperationOutcome.OK,
    DiagnosticStatus.FAILED: OperationOutcome.ERROR,
}


@runtime_checkable
class ScorerFn(Protocol):
    """外部评估后端的可选打分回调。"""

    def __call__(self, name: str, value: float, attributes: dict[str, Any]) -> None: ...


@runtime_checkable
class BackendBridge(Protocol):
    """外部观测后端桥。"""

    def attach(self, hub: ObservabilityHub) -> None: ...

    def close(self) -> None: ...


class ObservabilityHub(ObservabilityBackend):
    """事件账本、投影插件与 OTel 外部导出的组合根。"""

    def __init__(
        self,
        exporters: Sequence[SpanExporter] = (),
        *,
        policy: AttributePolicy | None = None,
        sampling_rate: float = 1.0,
        service_name: str = _DEFAULT_SERVICE_NAME,
        environment: str | None = None,
        journal_projectors: Sequence[JournalProjector] = (),
        diagnostic_sinks: Sequence[DiagnosticSink] = (),
    ) -> None:
        sampler = (
            ParentBased(ALWAYS_ON)
            if sampling_rate >= 1.0
            else ParentBased(TraceIdRatioBased(sampling_rate))
        )
        resource_attrs: dict[str, str] = {_SERVICE_NAME_KEY: service_name}
        if environment:
            resource_attrs[LANGFUSE_ENVIRONMENT] = environment
        self._provider = TracerProvider(resource=Resource.create(resource_attrs), sampler=sampler)
        self._processors: list[SimpleSpanProcessor] = []
        for exporter in exporters:
            processor = SimpleSpanProcessor(_IsolatedExporter(exporter))
            self._provider.add_span_processor(processor)
            self._processors.append(processor)
        self._tracer = self._provider.get_tracer(_TRACER_NAME)
        self._policy = policy if policy is not None else AttributePolicy()
        self._diagnostic_sinks = tuple(diagnostic_sinks)
        projections: list[JournalProjector] = [OtelProjector(self._tracer), *journal_projectors]
        if self._diagnostic_sinks:
            projections.append(DiagnosticJsonlProjection(self._diagnostic_sinks))
        self._registry = ProjectionRegistry(projections)
        self._store = RunStore(policy=self._policy, registry=self._registry)
        self._scorers: list[ScorerFn] = []
        self._bridges: list[BackendBridge] = []
        self._released = False
        self._disposed = False

    @property
    def policy(self) -> AttributePolicy:
        return self._policy

    @property
    def store(self) -> RunStore:
        return self._store

    @property
    def provider(self) -> TracerProvider:
        return self._provider

    @property
    def exporters(self) -> list[SpanExporter]:
        return [processor.span_exporter.inner for processor in self._processors]  # type: ignore[attr-defined]

    @property
    def diagnostic_sinks(self) -> tuple[DiagnosticSink, ...]:
        """诊断 JSONL 的兼容输出接收器；它们不是独立事件流。"""
        return self._diagnostic_sinks

    def open_span(
        self,
        name: str,
        attributes: dict[str, Any],
        *,
        actor_role: str = "",
        actor_step: int | None = None,
        attach: bool = True,
    ) -> SpanHandle:
        attrs = dict(attributes)
        if actor_role and ATTR_AGENT_ROLE not in attrs:
            attrs[ATTR_AGENT_ROLE] = actor_role
        if actor_step is not None and ATTR_STEP not in attrs:
            attrs[ATTR_STEP] = actor_step
        span = self._tracer.start_span(name, attributes=self._policy.prepare(attrs))
        return SpanHandle(self, span, attrs, attach=attach)

    def emit_event(self, name: str, attributes: dict[str, Any]) -> None:
        prepared = self._policy.prepare(attributes)
        current = otel_trace.get_current_span()
        if current.is_recording():
            current.add_event(name, prepared)
            return
        span = self._tracer.start_span(name, attributes=prepared)
        span.end()

    def emit_diagnostic(
        self,
        *,
        category: DiagnosticCategory,
        operation: str,
        plugin: str,
        status: DiagnosticStatus,
        attributes: dict[str, Any],
        output: dict[str, Any],
        causation_refs: tuple[str, ...] = (),
        duration_ms: int | None = None,
        error_type: str = "",
        error_message: str = "",
        actor_role: str = "",
        actor_step: int | None = None,
    ) -> StampedEvent:
        """以 ``RuntimeObserved`` 追加插件和运行解释记录。"""
        refs = tuple(
            int(ref.removeprefix("journal:"))
            for ref in causation_refs
            if ref.removeprefix("journal:").isdigit()
        )
        return self._store.append(
            RuntimeObserved(
                kind=_KIND_BY_CATEGORY[category],
                operation=operation,
                source=plugin or actor_role or "runtime",
                outcome=_OUTCOME_BY_STATUS[status],
                duration_ms=duration_ms,
                attributes={"actor_role": actor_role, "actor_step": actor_step, **attributes},
                output=output,
                error_code=error_type,
                error_message=error_message,
                causation_refs=refs,
            )
        )

    def register_scorer(self, scorer: ScorerFn) -> None:
        self._scorers.append(scorer)

    def attach_bridge(self, bridge: BackendBridge) -> None:
        bridge.attach(self)
        self._bridges.append(bridge)

    @property
    def bridges(self) -> tuple[BackendBridge, ...]:
        return tuple(self._bridges)

    def score(self, name: str, value: float, attributes: dict[str, Any]) -> None:
        for scorer in self._scorers:
            try:
                scorer(name, value, attributes)
            except Exception:
                _log.warning("score_backend_failed", score_name=name)
        if not self._scorers:
            self.emit_event(f"score.{name}", {"value": value, **attributes})

    def flush(self) -> None:
        self._store.flush()
        for processor in self._processors:
            processor.force_flush(timeout_millis=2_000)

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._store.close()

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        for processor in self._processors:
            processor.force_flush(timeout_millis=2_000)
        for processor in self._processors:
            processor.shutdown()
        for bridge in self._bridges:
            try:
                bridge.close()
            except Exception:
                _log.warning("observability_bridge_close_failed", bridge=type(bridge).__name__)

    def close(self) -> None:
        self.release()
        self.dispose()


__all__ = ["BackendBridge", "ObservabilityHub", "ScorerFn"]
