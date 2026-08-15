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
    RunInsight,
    RunScope,
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
    JOURNAL_CATALOG,
    JOURNAL_CATALOG_META,
    JOURNAL_EVENT_CLASSES,
    JournalSchemaMeta,
)
from lca.contracts.protocols import JournalProjector
from lca.layer0_infra.observability.exporters.langfuse import ExporterUnavailableError
from lca.layer0_infra.observability.facade import (
    SpanContext,
    annotate,
    bind,
    current_hub,
    detached_span,
    event,
    get_span_context,
    record,
    score,
    set_actor,
    set_session,
    span,
    traced,
)
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
from lca.layer0_infra.observability.registry import (
    UnknownExporterError,
    create_observability,
)
from lca.layer0_infra.observability.settings import ObservabilitySettings
from lca.layer0_infra.observability.team_profile import (
    TeamTraceProfile,
    objective_preview,
    team_id_for,
)
from lca.layer0_infra.observability.view import SpanView

__all__ = [
    "FRAMEWORK_TAG",
    "JOURNAL_CATALOG",
    "JOURNAL_CATALOG_META",
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
    "ExporterUnavailableError",
    "JournalEvent",
    "JournalProjector",
    "JournalSchemaMeta",
    "LlmCallCompleted",
    "LlmCallStarted",
    "ObservabilityHub",
    "ObservabilitySettings",
    "OtelProjector",
    "ReasoningCompleted",
    "ReasoningDelta",
    "RunActivity",
    "RunInsight",
    "RunScope",
    "RunState",
    "RunStatus",
    "RunStore",
    "SpanContext",
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
    "ToolInvoked",
    "ToolStarted",
    "UnknownExporterError",
    "UnregisteredJournalEventError",
    "Verbosity",
    "annotate",
    "bind",
    "create_observability",
    "current_hub",
    "detached_span",
    "event",
    "fold_run_state",
    "get_current_run_scope",
    "get_span_context",
    "langfuse_span_visible",
    "objective_preview",
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
