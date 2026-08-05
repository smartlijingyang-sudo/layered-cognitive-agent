"""ObservabilityHub —— 可观测性唯一门面对象。

持有 OTel TracerProvider（遥测骨干）+ 导出器集合 + 属性策略；
业务层通过包根 ambient API（bind/span/event）间接使用本类，
永不直接接触 OTel 或后端。

导出器故障隔离：每个导出器包在 ``_IsolatedExporter`` 中，
单个后端异常只记 structlog，不中断 run。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import structlog
from opentelemetry import context as otel_context
from opentelemetry import trace as otel_trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBased, TraceIdRatioBased
from opentelemetry.trace import StatusCode

from lca.contracts.protocols import ObservabilityBackend
from lca.contracts.telemetry import (
    ATTR_AGENT_ROLE,
    ATTR_OBJECTIVE_PREVIEW,
    ATTR_SESSION_ID,
    ATTR_STEP,
    SpanName,
)
from lca.layer0_infra.observability.policy import AttributePolicy

if TYPE_CHECKING:
    from opentelemetry.context import Context, Token

_log = structlog.get_logger("lca.observability")

_TRACER_NAME = "lca"
_SERVICE_NAME_KEY = "service.name"
_DEFAULT_SERVICE_NAME = "lca"
_ERROR_MESSAGE_MAX = 500
"""错误消息属性截断上限（避免超长堆栈撑爆 trace）。"""

_ROOT_SPAN_NAMES = frozenset({SpanName.RUN_TEAM.value, SpanName.RUN_AGENT.value})

# Langfuse 后端约定属性键（自托管 v3/v4 实证；仅 L0 感知，业务层不可见）
_LANGFUSE_TRACE_NAME = "langfuse.trace.name"
_LANGFUSE_TRACE_INPUT = "langfuse.trace.input"
_LANGFUSE_SESSION_ID = "session.id"


class _IsolatedExporter(SpanExporter):
    """故障隔离包装：导出异常只记日志，永不向上传播。"""

    def __init__(self, inner: SpanExporter) -> None:
        self._inner = inner

    @property
    def inner(self) -> SpanExporter:
        return self._inner

    def export(self, spans: Sequence[Any]) -> SpanExportResult:
        try:
            return self._inner.export(spans)
        except Exception:
            _log.warning("span_export_failed", exporter=type(self._inner).__name__)
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        try:
            self._inner.shutdown()
        except Exception:
            _log.warning("exporter_shutdown_failed", exporter=type(self._inner).__name__)

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        try:
            return self._inner.force_flush(timeout_millis)
        except Exception:
            _log.warning("exporter_flush_failed", exporter=type(self._inner).__name__)
            return False


class SpanHandle:
    """span 可变句柄：``attributes`` 字典式写入，退出时统一过策略并落 OTel。

    进入时把 span attach 到 OTel 上下文——嵌套 span/事件以此为父
    （等价于 start_as_current_span 语义）；退出时 detach。
    用法由包根 ``span()`` 提供，业务层不直接构造。
    """

    def __init__(self, hub: ObservabilityHub, otel_span: Any, attributes: dict[str, Any]) -> None:
        self._hub = hub
        self._otel = otel_span
        self.attributes: dict[str, Any] = attributes
        self._ctx_token: Token[Context] | None = None

    def __enter__(self) -> SpanHandle:
        self._ctx_token = otel_context.attach(otel_trace.set_span_in_context(self._otel))
        return self

    def mark_error(self, message: str = "") -> None:
        """显式标记 span 为错误（异常被内部捕获未传播时使用）。"""
        self._otel.set_status(StatusCode.ERROR)
        if message:
            self.attributes.setdefault("error_message", message[:_ERROR_MESSAGE_MAX])

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        del tb
        if exc is not None:
            self.attributes.setdefault("error_type", type(exc).__name__)
            self.attributes.setdefault("error_message", str(exc)[:_ERROR_MESSAGE_MAX])
            self._otel.record_exception(exc)
            self._otel.set_status(StatusCode.ERROR)
        prepared = self._hub.policy.prepare(self.attributes)
        for key, value in prepared.items():
            self._otel.set_attribute(key, value)
        self._otel.end()
        if self._ctx_token is not None:
            otel_context.detach(self._ctx_token)


class NullSpanHandle:
    """未 bind hub 时的空句柄：属性写入被安全丢弃。"""

    def __init__(self) -> None:
        self.attributes: dict[str, Any] = {}

    def __enter__(self) -> NullSpanHandle:
        return self

    def mark_error(self, message: str = "") -> None:
        return None

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        return None


class ObservabilityHub(ObservabilityBackend):
    """可观测性唯一门面：OTel 骨干 + 导出器 + 属性策略 + 生命周期。"""

    def __init__(
        self,
        exporters: Sequence[SpanExporter] = (),
        *,
        policy: AttributePolicy | None = None,
        sampling_rate: float = 1.0,
        service_name: str = _DEFAULT_SERVICE_NAME,
    ) -> None:
        sampler = (
            ParentBased(ALWAYS_ON)
            if sampling_rate >= 1.0
            else ParentBased(TraceIdRatioBased(sampling_rate))
        )
        self._provider = TracerProvider(
            resource=Resource.create({_SERVICE_NAME_KEY: service_name}),
            sampler=sampler,
        )
        self._processors: list[SimpleSpanProcessor] = []
        for exporter in exporters:
            processor = SimpleSpanProcessor(_IsolatedExporter(exporter))
            self._provider.add_span_processor(processor)
            self._processors.append(processor)
        self._tracer = self._provider.get_tracer(_TRACER_NAME)
        self._policy = policy if policy is not None else AttributePolicy()
        self._scorer: Any = None
        self._bridges: list[Any] = []

    # ── 属性 ────────────────────────────────────────────
    @property
    def policy(self) -> AttributePolicy:
        return self._policy

    @property
    def provider(self) -> TracerProvider:
        return self._provider

    @property
    def exporters(self) -> list[SpanExporter]:
        return [p.span_exporter.inner for p in self._processors]  # type: ignore[attr-defined]

    # ── 发射（facade 调用）─────────────────────────────
    def open_span(
        self,
        name: str,
        attributes: dict[str, Any],
        *,
        actor_role: str = "",
        actor_step: int | None = None,
    ) -> SpanHandle:
        """打开一个 span；actor 身份自动盖章（显式属性优先）。"""
        attrs = dict(attributes)
        if actor_role and ATTR_AGENT_ROLE not in attrs:
            attrs[ATTR_AGENT_ROLE] = actor_role
        if actor_step is not None and ATTR_STEP not in attrs:
            attrs[ATTR_STEP] = actor_step
        if name in _ROOT_SPAN_NAMES:
            attrs.update(self._backend_root_attrs(attrs))
        otel_span = self._tracer.start_span(name, attributes=self._policy.prepare(dict(attrs)))
        return SpanHandle(self, otel_span, attrs)

    def _backend_root_attrs(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """根 span 的后端约定属性（Langfuse trace/session 映射）。"""
        out: dict[str, Any] = {}
        session = attrs.get(ATTR_SESSION_ID)
        if session:
            out[_LANGFUSE_SESSION_ID] = session
        objective = attrs.get(ATTR_OBJECTIVE_PREVIEW)
        if objective:
            out[_LANGFUSE_TRACE_INPUT] = objective
        return out

    def emit_event(self, name: str, attributes: dict[str, Any]) -> None:
        """业务事件：优先挂当前 span；无活跃 span 时落零时长 span。"""
        prepared = self._policy.prepare(attributes)
        current = otel_trace.get_current_span()
        if current.is_recording():
            current.add_event(name, prepared)
            return
        span = self._tracer.start_span(name, attributes=prepared)
        span.end()

    def register_scorer(self, scorer: Any) -> None:
        """后端评估钩子（Langfuse 导出器装配时注入）。"""
        self._scorer = scorer

    def attach_bridge(self, bridge: Any) -> None:
        """挂接外部后端桥（如 LangfuseBridge）：接管 provider 导出与生命周期。"""
        bridge.attach(self)
        self._bridges.append(bridge)

    def score(self, name: str, value: float, attributes: dict[str, Any]) -> None:
        """评估打分：后端支持走 scorer，否则降级为事件。"""
        if self._scorer is not None:
            try:
                self._scorer(name, value, attributes)
                return
            except Exception:
                _log.warning("score_backend_failed", score_name=name)
        self.emit_event(f"score.{name}", {"value": value, **attributes})

    # ── 生命周期 ────────────────────────────────────────
    def flush(self) -> None:
        for processor in self._processors:
            processor.force_flush()
        for bridge in self._bridges:
            bridge.flush()

    def close(self) -> None:
        self.flush()
        for processor in self._processors:
            processor.shutdown()
        for bridge in self._bridges:
            bridge.close()
