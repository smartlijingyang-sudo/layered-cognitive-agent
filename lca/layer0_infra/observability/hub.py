"""ObservabilityHub —— 可观测性唯一门面对象。

持有 OTel TracerProvider（遥测骨干）+ 导出器集合 + 属性策略 +
RunStore（ADR-0055 唯一写入仲裁）；业务层通过包根 ambient API
（bind/span/event/record）间接使用本类，永不直接接触 OTel 或后端。

导出器故障隔离：每个导出器包在 ``_IsolatedExporter`` 中，
单个后端异常只记 structlog，不中断 run（机制件见 handles 模块）。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import structlog
from opentelemetry import trace as otel_trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBased, TraceIdRatioBased

from lca.contracts.atoms.telemetry import (
    ATTR_AGENT_ROLE,
    ATTR_STEP,
)
from lca.contracts.protocols import JournalProjector, ObservabilityBackend
from lca.layer0_infra.observability.handles import (
    SpanHandle,
    _IsolatedExporter,
)
from lca.layer0_infra.observability.journal.engine import RunStore
from lca.layer0_infra.observability.journal.insight_engine import InsightEngine
from lca.layer0_infra.observability.journal.otel_projector import OtelProjector
from lca.layer0_infra.observability.langfuse_conventions import (
    LANGFUSE_ENVIRONMENT,
)
from lca.layer0_infra.observability.policy import AttributePolicy

_log = structlog.get_logger("lca.observability")

_TRACER_NAME = "lca"
_SERVICE_NAME_KEY = "service.name"
_DEFAULT_SERVICE_NAME = "lca"


class ObservabilityHub(ObservabilityBackend):
    """可观测性唯一门面：OTel 骨干 + 导出器 + 属性策略 + 生命周期。"""

    def __init__(
        self,
        exporters: Sequence[SpanExporter] = (),
        *,
        policy: AttributePolicy | None = None,
        sampling_rate: float = 1.0,
        service_name: str = _DEFAULT_SERVICE_NAME,
        environment: str | None = None,
        journal_projectors: Sequence[JournalProjector] = (),
    ) -> None:
        sampler = (
            ParentBased(ALWAYS_ON)
            if sampling_rate >= 1.0
            else ParentBased(TraceIdRatioBased(sampling_rate))
        )
        resource_attrs: dict[str, str] = {_SERVICE_NAME_KEY: service_name}
        if environment:
            # 资源级 environment → Langfuse 环境维度（隔离测试/生产 trace）
            resource_attrs[LANGFUSE_ENVIRONMENT] = environment
        self._provider = TracerProvider(
            resource=Resource.create(resource_attrs),
            sampler=sampler,
        )
        self._processors: list[SimpleSpanProcessor] = []
        for exporter in exporters:
            processor = SimpleSpanProcessor(_IsolatedExporter(exporter))
            self._provider.add_span_processor(processor)
            self._processors.append(processor)
        self._tracer = self._provider.get_tracer(_TRACER_NAME)
        self._policy = policy if policy is not None else AttributePolicy()
        # RunStore 永远在线（ADR-0055）。subscriber 顺序即语义：
        # InsightEngine 先行（收尾时把 RunInsight 通过 store.append 注入，
        # 须在 OTel 关闭 run span、console 渲染 Run Card 之前完成），
        # 随后 OtelProjector（span 平面由叙事驱动），
        # 最后按后端配置装配其余 subscriber（console/jsonl...）。
        insight = InsightEngine()
        self._store = RunStore(
            [insight, OtelProjector(self._tracer), *journal_projectors], policy=self._policy
        )
        insight.bind_store(self._store)
        self._scorer: Any = None
        self._bridges: list[Any] = []
        self._released = False
        self._disposed = False

    # ── 属性 ────────────────────────────────────────────
    @property
    def policy(self) -> AttributePolicy:
        return self._policy

    @property
    def store(self) -> RunStore:
        """RunStore（ADR-0055）：唯一写入仲裁。"""
        return self._store

    @property
    def journal(self) -> RunStore:
        """向后兼容别名——新代码请使用 ``hub.store``。"""
        return self._store

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
        attach: bool = True,
    ) -> SpanHandle:
        """打开一个 span；actor 身份自动盖章（显式属性优先）。

        ``attach=False``：span 不成为 ambient 当前 span（detached），
        块内发射的内容仍挂外层父节点——用于生命周期脚手架 span。
        """
        attrs = dict(attributes)
        if actor_role and ATTR_AGENT_ROLE not in attrs:
            attrs[ATTR_AGENT_ROLE] = actor_role
        if actor_step is not None and ATTR_STEP not in attrs:
            attrs[ATTR_STEP] = actor_step
        otel_span = self._tracer.start_span(name, attributes=self._policy.prepare(dict(attrs)))
        return SpanHandle(self, otel_span, attrs, attach=attach)

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

    @property
    def bridges(self) -> tuple[Any, ...]:
        """已挂接的外部后端桥（如 Langfuse）。只读。"""
        return tuple(self._bridges)

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
        """Journal only. Exporters flush in dispose(), never on the chat path."""
        self._store.flush()

    def release(self) -> None:
        """Close store subscribers (jsonl, LiveTail). Chat SSE can end here.

        Must not wait for optional exporters. Gateway finalize calls this
        before any Langfuse/OTel teardown.
        """
        if self._released:
            return
        self._released = True
        self._store.close()

    def dispose(self) -> None:
        """Best-effort exporter shutdown. Caller must not hold the event loop."""
        if self._disposed:
            return
        self._disposed = True
        for processor in self._processors:
            processor.force_flush(timeout_millis=2_000)
        for processor in self._processors:
            processor.shutdown()
        for bridge in self._bridges:
            bridge.close()

    def close(self) -> None:
        """Tests / CLI: release live readers, then dispose exporters."""
        self.release()
        self.dispose()
