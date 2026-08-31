"""LCA 可观测性子系统 —— 唯一公共面（白名单守卫）。

架构三层（Hexagonal / Ports & Adapters）：
    ① 契约层（contracts）—— Protocol + 数据类（JournalEvent / RunContext / 端口）
    ② 装配层（harness/observability）—— assemble_observability() 把 plugin 装成 BoundObservability
    ③ 实现层（journal_backend / tracer_backend / readers）—— adapter，plugin 化

外部使用（唯一入口）::

    from lca.infrastructure.observability import (
        record, span, annotate, score,         # dispatch API
        bind, set_actor, set_session,          # RunContext 控制
        record_runtime, record_operation,      # 语义化运行时事件
        BoundObservability, RunContext,        # 值对象
    )

    record(AgentRunStarted(...))
    with span(SpanName.LLM_CHAT) as h:
        h.attributes["model"] = "qwen"

包外禁止 import 任何子模块（守卫测试强制）；本 ``__init__`` 是唯一表面。
"""

from lca.contracts.models.observability.diagnostic import (
    DiagnosticCategory,
    DiagnosticEvent,
    DiagnosticStatus,
)
from lca.contracts.models.observability.event import (
    EventAudience,
    EventDescriptor,
    EventDurability,
    EventPlane,
    EventSensitivity,
    OperationOutcome,
    RuntimeKind,
)
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
    DelegationMechanism,
    JournalEvent,
    LlmCallCompleted,
    LlmCallStarted,
    PluginAuthored,
    PluginInspected,
    PluginMounted,
    PluginMountRejected,
    PluginUnmounted,
    PresetPublished,
    ReasoningCompleted,
    ReasoningDelta,
    RunActivity,
    RunScope,
    RuntimeObserved,
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
from lca.contracts.models.observability.journal_catalog import (
    JOURNAL_EVENT_CLASSES,
    JournalSchemaMeta,
)
from lca.contracts.observability.named_registry import NamedRegistry
from lca.contracts.protocols import JournalProjector
from lca.infrastructure.observability.event_catalog import (
    EVENT_DESCRIPTOR_REGISTRY,
    descriptor_for,
    may_export_externally,
)
from lca.infrastructure.observability.event_descriptor_env import (
    bind_descriptors,
    current_descriptors,
)
from lca.infrastructure.observability.event_descriptor_registry import (
    DuplicateEventDescriptorError,
    InMemoryEventDescriptorRegistry,
    UnknownEventDescriptorError,
)
from lca.infrastructure.observability.event_descriptors_data import build_default_registry
from lca.infrastructure.observability.facade import (  # noqa: F401
    BoundObservability,
    EvidenceBinding,
    OperationRecorder,
    RunContext,
    SpanContextInfo,
    annotate,
    bind,
    bind_backends,
    current_bound,
    current_context,
    detached_span,
    get_span_context,
    record,
    record_operation,
    record_runtime,
    score,
    set_actor,
    set_session,
    span,
    traced,
)
from lca.infrastructure.observability.genai import (
    LlmGenAIMapper,
    ToolGenAIMapper,
)
from lca.infrastructure.observability.genai import (
    build_default_registry as build_default_genai_registry,
)
from lca.infrastructure.observability.journal import (
    OtelProjector,
    RunState,
    RunStatus,
    RunStore,
    UnregisteredJournalEventError,
    fold_run_state,
)
from lca.infrastructure.observability.journal.backends import InMemoryJournalStore
from lca.infrastructure.observability.journal.engine.journal_io import (
    read_journal,
    stamped_to_record,
)
from lca.infrastructure.observability.journal.engine.serialization import stamped_to_journal_record
from lca.infrastructure.observability.langfuse_conventions import (
    FRAMEWORK_TAG,
    LANGFUSE_ENVIRONMENT,
    LANGFUSE_OBSERVATION_INPUT,
    LANGFUSE_OBSERVATION_METADATA_AGENT_ROLE,
    LANGFUSE_OBSERVATION_MODEL_NAME,
    LANGFUSE_OBSERVATION_OUTPUT,
    LANGFUSE_OBSERVATION_TYPE,
    LANGFUSE_OBSERVATION_USAGE_DETAILS,
    LANGFUSE_TRACE_TAGS,
    OBSERVATION_TYPE_AGENT,
    OBSERVATION_TYPE_GENERATION,
    OBSERVATION_TYPE_TOOL,
    langfuse_span_visible,
)
from lca.infrastructure.observability.narrative import plan_steps_joined
from lca.infrastructure.observability.policy import AttributePolicy, Verbosity
from lca.infrastructure.observability.projection_registry import EventProjection, ProjectionRegistry
from lca.infrastructure.observability.run_context import (
    TEAM_CONTAINER_ROLE,
    adopt_run_scope,
    get_current_run_scope,
    run_scope,
)
from lca.infrastructure.observability.settings import ObservabilitySettings
from lca.infrastructure.observability.team_profile import (
    TeamTraceProfile,
    objective_preview,
    team_id_for,
)
from lca.infrastructure.observability.trace_inspector import TraceInspector, TraceReport
from lca.infrastructure.observability.trace_tool_runner import (
    make_explain_failure_tool,
    make_export_minimal_reproduction_tool,
    make_find_optimization_tool,
    make_inspect_trace_tool,
    make_plugin_interaction_graph_tool,
)
from lca.infrastructure.observability.tracer_backend import OtelTracer
from lca.infrastructure.observability.view import SpanView

__all__ = [
    "EVENT_DESCRIPTOR_REGISTRY",
    "FRAMEWORK_TAG",
    "JOURNAL_EVENT_CLASSES",
    "LANGFUSE_ENVIRONMENT",
    "LANGFUSE_OBSERVATION_INPUT",
    "LANGFUSE_OBSERVATION_METADATA_AGENT_ROLE",
    "LANGFUSE_OBSERVATION_MODEL_NAME",
    "LANGFUSE_OBSERVATION_OUTPUT",
    "LANGFUSE_OBSERVATION_TYPE",
    "LANGFUSE_OBSERVATION_USAGE_DETAILS",
    "LANGFUSE_TRACE_TAGS",
    "OBSERVATION_TYPE_AGENT",
    "OBSERVATION_TYPE_GENERATION",
    "OBSERVATION_TYPE_TOOL",
    "TEAM_CONTAINER_ROLE",
    "ActionDegraded",
    "AgentRunFinished",
    "AgentRunStarted",
    "AttributePolicy",
    "BoundObservability",
    "CastingCompleted",
    "CastingFailed",
    "CastingStarted",
    "DecisionMade",
    "DelegationCacheHit",
    "DelegationCompleted",
    "DelegationIssued",
    "DelegationMechanism",
    "DiagnosticCategory",
    "DiagnosticEvent",
    "DiagnosticStatus",
    "DuplicateEventDescriptorError",
    "EventAudience",
    "EventDescriptor",
    "EventDurability",
    "EventPlane",
    "EventProjection",
    "EventSensitivity",
    "InMemoryEventDescriptorRegistry",
    "InMemoryJournalStore",
    "JournalEvent",
    "JournalProjector",
    "JournalSchemaMeta",
    "JournalStoreBackend",
    "LlmCallCompleted",
    "LlmCallStarted",
    "LlmGenAIMapper",
    "NamedRegistry",
    "ObservabilitySettings",
    "OperationOutcome",
    "OperationRecorder",
    "OtelProjector",
    "OtelTracer",
    "PluginAuthored",
    "PluginInspected",
    "PluginMountRejected",
    "PluginMounted",
    "PluginUnmounted",
    "PresetPublished",
    "ProjectionRegistry",
    "ReasoningCompleted",
    "ReasoningDelta",
    "RunActivity",
    "RunContext",
    "RunScope",
    "RunState",
    "RunStatus",
    "RunStore",
    "RuntimeKind",
    "RuntimeObserved",
    "SpanContextInfo",
    "SpanView",
    "StampedEvent",
    "StepCompleted",
    "StepTextDelta",
    "SynthesisCompleted",
    "TeamRunFinished",
    "TeamRunStarted",
    "TeamTraceProfile",
    "ToolCallStreaming",
    "ToolDenied",
    "ToolGenAIMapper",
    "ToolInvoked",
    "ToolStarted",
    "TraceInspector",
    "TraceReport",
    "TraceTool",
    "UnknownEventDescriptorError",
    "UnregisteredJournalEventError",
    "Verbosity",
    "adopt_run_scope",
    "annotate",
    "bind",
    "bind_backends",
    "bind_descriptors",
    "build_default_genai_registry",
    "build_default_registry",
    "current_bound",
    "current_context",
    "current_descriptors",
    "descriptor_for",
    "detached_span",
    "fold_run_state",
    "get_current_run_scope",
    "get_span_context",
    "langfuse_span_visible",
    "make_explain_failure_tool",
    "make_export_minimal_reproduction_tool",
    "make_find_optimization_tool",
    "make_inspect_trace_tool",
    "make_plugin_interaction_graph_tool",
    "may_export_externally",
    "objective_preview",
    "plan_steps_joined",
    "read_journal",
    "record",
    "record_operation",
    "record_runtime",
    "run_scope",
    "score",
    "set_actor",
    "set_session",
    "span",
    "stamped_to_journal_record",
    "stamped_to_record",
    "team_id_for",
    "traced",
]
