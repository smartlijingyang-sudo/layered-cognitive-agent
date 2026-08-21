"""契约协议包 —— 全量 re-export，保持 ``from lca.contracts.protocols import X`` 兼容。
子模块按层拆分：
infra / cognition / embodiment / memory / runtime / agent / orchestration
跨层机制见 ``lca.contracts.mechanisms``，跨层纯类型见 ``lca.contracts.models.core``。
"""

from __future__ import annotations

# ── 跨层机制（re-exported from mechanisms for convenience）──
from lca.contracts.mechanisms import (
    ComponentRegistryProtocol,
    EventBus,
    Hook,
    HookRegistry,
    NamedRegistryProtocol,
    OrchestrationRegistryProtocol,
)

# ── 纯数据类型 ───────────────────────────────────────────
from lca.contracts.models.core.stop import StopOutcome

# ── L3 Agent / Team 入口 ──────────────────────────────────
from lca.contracts.protocols.agent import (
    AgentUnit,
    BudgetAware,
    BudgetPolicy,
    TeamUnit,
)

# ── 可选能力（无 bind/install 组装面）────────────
from lca.contracts.protocols.capabilities import HasHooks

# ── CapabilityPlan + 11 关系代数（ADR-0068 §一 + ADR-0069 §三）──────
from lca.contracts.protocols.capability_plan import (
    CapabilityPlan,
    ProviderBinding,
    capability_plan_hash,
    capability_plan_to_dict,
    provider_bindings_from_iter,
    relations_from_plugin,
    relations_of_kind,
    relations_to_plugin,
)

# ── 自动组队（角色库与选角契约，ADR-0042）────────
from lca.contracts.protocols.casting import RoleLibrary, TeamCaster

# ── L1 认知 / Brain 协议 ─────────────────────────────────
from lca.contracts.protocols.cognition import (
    Brain,
    BrainFactory,
    Critic,
    DecisionGate,
    PerceiveHub,
    Reasoner,
    Sensor,
    SensorDisabled,
    SkillRouter,
    SupportsShortcut,
)

# ── CommandEnvelope + RunFact (ADR-0068 §五 + ADR-0074 PR-7 V4) ─────────
from lca.contracts.protocols.command_envelope import (
    BudgetReservation,
    CapabilityGrant,
    CommandEnvelope,
    DecisionRef,
    EnvelopeVerdict,
    RunDelta,
    RunFact,
    Verdict,
    command_envelope_to_dict,
    envelope_aggregate_verdict,
    envelope_is_authorized,
    mint_envelope,
    warn_deprecated_envelope_constructor,
)

# ── 控制面单一入口（ADR-0066 + tracker §19）─────────────────────
from lca.contracts.protocols.control_plan import (
    ALLOWED_OPERATORS,
    SLOT_DEFAULT_AGGREGATION,
    SLOT_DEFAULT_FAILURE,
    Activation,
    AggregationMode,
    ControlEntry,
    ControlPlan,
    FailureMode,
    always,
    compute_control_plan_hash,
)

# ── L1 Body / 行动执行协议 ───────────────────────────────
from lca.contracts.protocols.embodiment import Body

# ── L0 基础设施协议 ──────────────────────────────────────
from lca.contracts.protocols.infra import (
    AgentTransport,
    AttachmentIdentity,
    LLMAdapter,
    SafeExecutor,
    Sandbox,
    SandboxRuntime,
    StateStore,
    Tool,
    ToolRegistry,
    TransportRegistryProtocol,
)

# ── 执行日志投影协议（ADR-0037 Journal-as-Truth）────────
from lca.contracts.protocols.journal import JournalProjector

# ── LogicAddress 6 维（ADR-0069 §二 + ADR-0074 V9）────────────────
from lca.contracts.protocols.logic_address import (
    LogicAddress,
    LogicAddressScore,
    canonical_scope_of,
    declared_dim_count,
    is_complete_address,
    score_logic_address,
)

# ── L1 Memory 协议 ───────────────────────────────────────
from lca.contracts.protocols.memory import MemorySystem, RetrievalPolicy

# ── 可观测性协议（业务层唯一发射门面）──────────────────
from lca.contracts.protocols.observability import (
    ObservabilityBackend,
    Telemetry,
)

# ── 操作技能库（与角色库平行，ADR-0048）────────────
from lca.contracts.protocols.operational_skills import (
    SANDBOX_SKILL_MOUNT_PREFIX,
    SkillImporter,
    SkillImportError,
    SkillIndexEntry,
    SkillNotFoundError,
    SkillPackage,
    SkillPackageStore,
    SkillSearchResult,
)

# ── L3 团队编排协议 ──────────────────────────────────────
from lca.contracts.protocols.orchestration import (
    MemberInvoker,
    SharedMemoryStore,
    Synthesizer,
    TeamAssembly,
    TeamStage,
    TeamStrategy,
)

# ── ScopePlan + CompiledRunPlan（ADR-0068 §一 + ADR-0074 PR-3）──────
from lca.contracts.protocols.plan import (
    COMPILED_RUN_PLAN_VERSION,
    CompiledRunPlan,
    build_input_provenance,
    compiled_run_plan_ref,
    compiled_run_plan_to_dict,
)

# ── CommandEnvelope + RunFact (ADR-0068 §五 + ADR-0074 PR-7 V4) ─────────
# ── L2 Runtime 协议 ──────────────────────────────────────
from lca.contracts.protocols.reducer import (
    LoopPhase,
    LoopPhaseKind,
    LoopTopology,
    Reducer,
)
from lca.contracts.protocols.relation import (
    TypedRelation,
    typed_relation_to_dict,
    typed_relations_from_iter,
)
from lca.contracts.protocols.runtime import Runtime, StopOutcomePolicy, StopRule
from lca.contracts.protocols.scope_plan import (
    BudgetCeiling,
    ScopePlan,
    scope_plan_from_iter,
    scope_plan_hash,
    scope_plan_to_dict,
)

# ── 工具执行管线（五阶段可拦截管线）────────────
from lca.contracts.protocols.tool_pipeline import (
    ToolDefinition,
    ToolExecutionContext,
    ToolExecutionPipeline,
    ToolExecutionResult,
    ToolPostDecision,
    ToolPreDecision,
    ToolProvider,
    ToolRenderer,
)

__all__ = [
    "ALLOWED_OPERATORS",
    "COMPILED_RUN_PLAN_VERSION",
    "SANDBOX_SKILL_MOUNT_PREFIX",
    "SLOT_DEFAULT_AGGREGATION",
    "SLOT_DEFAULT_FAILURE",
    "Activation",
    "AgentTransport",
    "AgentUnit",
    "AggregationMode",
    "AttachmentIdentity",
    "Body",
    "Brain",
    "BrainFactory",
    "BudgetAware",
    "BudgetCeiling",
    "BudgetPolicy",
    "BudgetReservation",
    "CapabilityGrant",
    "CapabilityPlan",
    "CommandEnvelope",
    "CompiledRunPlan",
    "ComponentRegistryProtocol",
    "ControlEntry",
    "ControlPlan",
    "Critic",
    "DecisionGate",
    "DecisionRef",
    "EnvelopeVerdict",
    "EventBus",
    "FailureMode",
    "HasHooks",
    "Hook",
    "HookRegistry",
    "JournalProjector",
    "LLMAdapter",
    "LogicAddress",
    "LogicAddressScore",
    "LoopPhase",
    "LoopPhaseKind",
    "LoopTopology",
    "MemberInvoker",
    "MemorySystem",
    "NamedRegistryProtocol",
    "ObservabilityBackend",
    "OrchestrationRegistryProtocol",
    "PerceiveHub",
    "ProviderBinding",
    "Reasoner",
    "Reducer",
    "RetrievalPolicy",
    "RoleLibrary",
    "RunDelta",
    "RunFact",
    "Runtime",
    "SafeExecutor",
    "Sandbox",
    "SandboxRuntime",
    "ScopePlan",
    "Sensor",
    "SensorDisabled",
    "SharedMemoryStore",
    "SkillImportError",
    "SkillImporter",
    "SkillIndexEntry",
    "SkillNotFoundError",
    "SkillPackage",
    "SkillPackageStore",
    "SkillRouter",
    "SkillSearchResult",
    "StateStore",
    "StopOutcome",
    "StopOutcomePolicy",
    "StopRule",
    "SupportsShortcut",
    "Synthesizer",
    "TeamAssembly",
    "TeamCaster",
    "TeamStage",
    "TeamStrategy",
    "TeamUnit",
    "Telemetry",
    "Tool",
    "ToolDefinition",
    "ToolExecutionContext",
    "ToolExecutionPipeline",
    "ToolExecutionResult",
    "ToolPostDecision",
    "ToolPreDecision",
    "ToolProvider",
    "ToolRegistry",
    "ToolRenderer",
    "TransportRegistryProtocol",
    "TypedRelation",
    "Verdict",
    "always",
    "build_input_provenance",
    "canonical_scope_of",
    "capability_plan_hash",
    "capability_plan_to_dict",
    "command_envelope_to_dict",
    "compiled_run_plan_ref",
    "compiled_run_plan_to_dict",
    "compute_control_plan_hash",
    "control_plan_to_dict",
    "declared_dim_count",
    "envelope_aggregate_verdict",
    "envelope_is_authorized",
    "is_complete_address",
    "is_slot_empty",
    "mint_envelope",
    "provider_bindings_from_iter",
    "relations_from_plugin",
    "relations_of_kind",
    "relations_to_plugin",
    "scope_plan_from_iter",
    "scope_plan_hash",
    "scope_plan_to_dict",
    "score_logic_address",
    "slot_entries",
    "slots_covered",
    "slots_missing",
    "typed_relation_to_dict",
    "typed_relations_from_iter",
    "warn_deprecated_envelope_constructor",
]
