"""LCA 可观测性子系统 —— 唯一公共面（白名单守卫）。

架构三层：
    ① 认知语义层（contracts 词表 + 本包 facade）—— 我们拥有
    ② 遥测骨干（OpenTelemetry）—— 业界标准，被 facade 封装，业务层不可见
    ③ 后端（console/jsonl/memory/langfuse）—— 注册表装配，配置化

外部使用（唯一入口）::

    from lca.layer0_infra.observability import create_observability, bind, span, event

    hub = create_observability("console+langfuse")   # 或 Agent(observability=...)
    with bind(hub):
        with span(SpanName.RUN_AGENT):
            ...

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
    get_current_run_scope,
    run_scope,
)
from lca.contracts.models.observability.journal_catalog import (
    JOURNAL_EVENT_CLASSES,
    JournalSchemaMeta,
)
from lca.contracts.protocols import JournalProjector
from lca.layer0_infra.observability.event_catalog import (
    EVENT_DESCRIPTOR_REGISTRY,
    descriptor_for,
    may_export_externally,
)
from lca.layer0_infra.observability.event_descriptor_registry import (
    DuplicateEventDescriptorError,
    InMemoryEventDescriptorRegistry,
    UnknownEventDescriptorError,
)
from lca.layer0_infra.observability.event_descriptors_data import build_default_registry
from lca.layer0_infra.observability.exporters.langfuse import ExporterUnavailableError
from lca.layer0_infra.observability.genai import (
    GenAISemanticMapperRegistry,
    LlmGenAIMapper,
    ToolGenAIMapper,
    build_default_registry as build_default_genai_registry,
)
from lca.layer0_infra.observability.journal.backends import InMemoryJournalStore
from lca.layer0_infra.observability.journal.journal_io import read_journal, stamped_to_record
from lca.layer0_infra.observability.trace_tool_runner import (
    make_explain_failure_tool,
    make_export_minimal_reproduction_tool,
    make_find_optimization_tool,
    make_inspect_trace_tool,
    make_plugin_interaction_graph_tool,
)
from lca.layer0_infra.observability.facade import (
    SpanContext,
    annotate,
    bind,
    current_hub,
    detached_span,
    event,
    get_span_context,
    observe,
    observe_operation,
    record,
    score,
    set_actor,
    set_session,
    span,
    traced,
)
from lca.contracts.observability.journal_store import JournalStoreBackend
from lca.contracts.observability.named_registry import NamedRegistry
from lca.layer0_infra.observability.hub import ObservabilityHub
from lca.layer0_infra.observability.journal import (
    OtelProjector,
    RunState,
    RunStatus,
    RunStore,
    UnregisteredJournalEventError,
    fold_run_state,
)
from lca.layer0_infra.observability.langfuse_conventions import (
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
from lca.layer0_infra.observability.narrative import plan_steps_joined
from lca.layer0_infra.observability.policy import AttributePolicy, Verbosity
from lca.layer0_infra.observability.projection_registry import EventProjection, ProjectionRegistry
from lca.layer0_infra.observability.registry import (
    UnknownExporterError,
    create_observability,
)
from lca.layer0_infra.observability.run_diagnostics import JsonlDiagnosticSink
from lca.layer0_infra.observability.settings import ObservabilitySettings
from lca.layer0_infra.observability.team_profile import (
    TeamTraceProfile,
    objective_preview,
    team_id_for,
)
from lca.layer0_infra.observability.trace_inspector import TraceInspector, TraceReport
from lca.layer0_infra.observability.view import SpanView

__all__ = [
    "DuplicateEventDescriptorError",
    "EVENT_DESCRIPTOR_REGISTRY",
    "FRAMEWORK_TAG",
    "InMemoryEventDescriptorRegistry",
    "InMemoryJournalStore",
    "JOURNAL_EVENT_CLASSES",
    "JournalStoreBackend",
    "LlmGenAIMapper",
    "NamedRegistry",
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
    "ActionDegraded",
    "AgentRunFinished",
    "AgentRunStarted",
    "AttributePolicy",
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
    "EventAudience",
    "EventDescriptor",
    "EventDurability",
    "EventPlane",
    "EventProjection",
    "EventSensitivity",
    "ExporterUnavailableError",
    "JournalEvent",
    "JournalProjector",
    "JournalSchemaMeta",
    "JsonlDiagnosticSink",
    "LlmCallCompleted",
    "LlmCallStarted",
    "ObservabilityHub",
    "ObservabilitySettings",
    "OperationOutcome",
    "OtelProjector",
    "ProjectionRegistry",
    "ReasoningCompleted",
    "ReasoningDelta",
    "RunActivity",
    "RunScope",
    "RunState",
    "RunStatus",
    "RunStore",
    "RuntimeKind",
    "RuntimeObserved",
    "SpanContext",
    "SpanView",
    "StampedEvent",
    "StepCompleted",
    "StepTextDelta",
    "SynthesisCompleted",
    "TeamRunFinished",
    "TeamRunStarted",
    "ToolGenAIMapper",
    "TeamTraceProfile",
    "ToolCallStreaming",
    "ToolDenied",
    "ToolInvoked",
    "ToolStarted",
    "TraceInspector",
    "TraceTool",
    "make_explain_failure_tool",
    "make_export_minimal_reproduction_tool",
    "make_find_optimization_tool",
    "make_inspect_trace_tool",
    "make_plugin_interaction_graph_tool",
    "read_journal",
    "stamped_to_record",
    "TraceReport",
    "UnknownEventDescriptorError",
    "UnknownExporterError",
    "UnregisteredJournalEventError",
    "Verbosity",
    "annotate",
    "bind",
    "build_default_genai_registry",
    "build_default_registry",
    "create_observability",
    "current_hub",
    "detached_span",
    "event",
    "fold_run_state",
    "get_current_run_scope",
    "get_span_context",
    "langfuse_span_visible",
    "objective_preview",
    "observe",
    "observe_operation",
    "plan_steps_joined",
    "record",
    "run_scope",
    "score",
    "set_actor",
    "set_session",
    "span",
    "team_id_for",
    "traced",
]
