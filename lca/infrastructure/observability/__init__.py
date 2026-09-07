"""LCA 可观测性子系统 —— 唯一公共面（白名单守卫）。

SSOT: :func:`Session.append` is the single durable-fact entry. The
legacy :class:`MemoryJournal` / :class:`RunStore` / :func:`facade.record`
path (ADR-0055) is kept for the boot-time journal backend assembly and
the graph-execution committer; it is not used by the LLM adapter any
more (see :mod:`lca.infrastructure.observability.adapters.adapters`).

外部使用（唯一定位）::

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

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lca.contracts.models.observability.diagnostic.diagnostic import (
    DiagnosticCategory,
    DiagnosticEvent,
    DiagnosticStatus,
)
from lca.contracts.models.observability.event.event import (
    EventAudience,
    EventDescriptor,
    EventDurability,
    EventPlane,
    EventSensitivity,
    OperationOutcome,
    RuntimeKind,
)
from lca.contracts.models.observability.journal.catalog import (
    JOURNAL_EVENT_CLASSES,
    JournalSchemaMeta,
)
from lca.contracts.models.observability.journal.journal import (
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
    RunScope,
    RuntimeObserved,
    StampedEvent,
    StepCompleted,
    StepTextDelta,
    SynthesisCompleted,
    TeamRunFinished,
    TeamRunStarted,
    ToolCallResolved,
    ToolDenied,
    ToolInvoked,
    ToolStarted,
)
from lca.contracts.observability.registry.named_registry import NamedRegistry
from lca.contracts.protocols import JournalProjector
from lca.infrastructure.observability.adapters.policy import AttributePolicy, Verbosity
from lca.infrastructure.observability.adapters.view import SpanView
from lca.infrastructure.observability.backends.langfuse_conventions import (
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
from lca.infrastructure.observability.backends.tracer_backend import OtelTracer
from lca.infrastructure.observability.events.event.catalog import (
    EVENT_DESCRIPTOR_REGISTRY,
    descriptor_for,
    may_export_externally,
)
from lca.infrastructure.observability.events.event.descriptor_env import (
    bind_descriptors,
    current_descriptors,
)
from lca.infrastructure.observability.events.event.descriptor_registry import (
    DuplicateEventDescriptorError,
    InMemoryEventDescriptorRegistry,
    UnknownEventDescriptorError,
)
from lca.infrastructure.observability.events.event.descriptors_data import build_default_registry
from lca.infrastructure.observability.facade.facade.facade import (  # noqa: F401
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
from lca.infrastructure.observability.facade.projection.registry import (
    EventProjection,
    ProjectionRegistry,
)
from lca.infrastructure.observability.facade.run.ambit import (
    RunAmbit,
    bind_run_ambit,
    current_attachment_ids,
    current_file_store,
    current_plan_ref,
    current_role,
    current_run_ambit,
    current_workspace,
)
from lca.infrastructure.observability.facade.run.context import (
    TEAM_CONTAINER_ROLE,
    adopt_run_scope,
    get_current_run_scope,
    run_scope,
)
from lca.infrastructure.observability.facade.settings.settings import ObservabilitySettings
from lca.infrastructure.observability.facade.team.profile import (
    TeamTraceProfile,
    objective_preview,
    team_id_for,
)
from lca.infrastructure.observability.narrative import plan_steps_joined
from lca.infrastructure.observability.stream.trace_inspector import TraceInspector, TraceReport
from lca.infrastructure.observability.stream.trace_tool_runner import (
    make_explain_failure_tool,
    make_export_minimal_reproduction_tool,
    make_find_optimization_tool,
    make_inspect_trace_tool,
    make_plugin_interaction_graph_tool,
)

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
    "JournalEvent",
    "JournalProjector",
    "JournalSchemaMeta",
    "LlmCallCompleted",
    "LlmCallStarted",
    "NamedRegistry",
    "ObservabilitySettings",
    "OperationOutcome",
    "OperationRecorder",
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
    "RunAmbit",
    "RunContext",
    "RunScope",
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
    "ToolCallResolved",
    "ToolDenied",
    "ToolInvoked",
    "ToolStarted",
    "TraceInspector",
    "TraceReport",
    "TraceTool",
    "UnknownEventDescriptorError",
    "Verbosity",
    "adopt_run_scope",
    "annotate",
    "bind",
    "bind_backends",
    "bind_descriptors",
    "bind_run_ambit",
    "current_attachment_ids",
    "current_bound",
    "current_context",
    "current_descriptors",
    "current_file_store",
    "current_plan_ref",
    "current_role",
    "current_run_ambit",
    "current_workspace",
    "descriptor_for",
    "detached_span",
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
    "record",
    "record_operation",
    "record_runtime",
    "run_scope",
    "score",
    "set_actor",
    "set_session",
    "span",
    "team_id_for",
    "traced",
]

# Legacy journal storage symbols (RunStore / RunState / fold_run_state /
# read_journal / UnregisteredJournalEventError / InMemoryJournalStore /
# stamped_to_record / stamped_to_journal_record) are kept lazy-loaded by
# PEP 562 __getattr__ so the boot-time journal backend assembly can resolve
# them without forcing every importer to pull the legacy storage tree.
if TYPE_CHECKING:
    from lca.infrastructure.observability.journal.backends.memory import InMemoryJournalStore
    from lca.infrastructure.observability.journal.engine.engine import (
        RunStore,
        UnregisteredJournalEventError,
    )
    from lca.infrastructure.observability.journal.engine.journal_io import (
        read_journal,
        stamped_to_record,
    )
    from lca.infrastructure.observability.journal.engine.reducer import (
        RunState,
        RunStatus,
        fold_run_state,
    )
    from lca.infrastructure.observability.journal.engine.serialization import (
        stamped_to_journal_record,
    )

_LAZY_JOURNAL_SYMBOLS: dict[str, tuple[str, str]] = {
    "InMemoryJournalStore": (
        "lca.infrastructure.observability.journal.backends",
        "InMemoryJournalStore",
    ),
    "RunState": ("lca.infrastructure.observability.journal", "RunState"),
    "RunStatus": ("lca.infrastructure.observability.journal", "RunStatus"),
    "RunStore": ("lca.infrastructure.observability.journal", "RunStore"),
    "UnregisteredJournalEventError": (
        "lca.infrastructure.observability.journal",
        "UnregisteredJournalEventError",
    ),
    "fold_run_state": ("lca.infrastructure.observability.journal", "fold_run_state"),
    "read_journal": (
        "lca.infrastructure.observability.journal.engine.journal_io",
        "read_journal",
    ),
    "stamped_to_record": (
        "lca.infrastructure.observability.journal.engine.journal_io",
        "stamped_to_record",
    ),
    "stamped_to_journal_record": (
        "lca.infrastructure.observability.journal.engine.serialization",
        "stamped_to_journal_record",
    ),
}


def __getattr__(name: str) -> Any:
    """PEP 562 lazy loader — journal 实现符号按需 import,不污染业务层 import 图。"""
    import importlib

    spec = _LAZY_JOURNAL_SYMBOLS.get(name)
    if spec is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(spec[0])
    value = getattr(module, spec[1])
    globals()[name] = value
    return value
