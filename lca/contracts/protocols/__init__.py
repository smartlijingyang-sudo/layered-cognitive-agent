"""契约协议包 —— 全量 re-export，保持 ``from lca.contracts.protocols import X`` 兼容。
子模块按层拆分：
infra / cognition / embodiment / memory / runtime / agent / orchestration
跨层机制见 ``lca.contracts.mechanisms``，跨层纯类型见 ``lca.contracts.models.core``。

This module is a re-export barrel: every ``from X import Y`` below is a
deliberate public re-export, not an unused import. ``__all__`` is the
explicit sorted list at the bottom of this file — adding a new symbol
requires appending both the import and an ``__all__`` entry.
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

# ── ActionHandler（ADR-0074 插件化行动处理器）────────
from lca.contracts.protocols.act.action_handler import ActionHandler, ActionHandlerRegistry

# ── CommandEnvelope + RunFact (ADR-0068 §五 + ADR-0074 PR-7 V4) ─────────
from lca.contracts.protocols.act.command_envelope import (
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

# ── EffectHandler 与 EffectHandlerRegistry（ADR-0074 / ADR-0068）──────
from lca.contracts.protocols.act.effect_handler import (
    EffectCapabilities,
    EffectHandler,
    EffectHandlerRegistry,
)

# ── L1 Body / 行动执行协议 ───────────────────────────────
from lca.contracts.protocols.act.embodiment import Body

# ── 工具执行管线（五阶段可拦截管线）────────────
from lca.contracts.protocols.act.tool_pipeline import (
    ToolDefinition,
    ToolExecutionContext,
    ToolExecutionPipeline,
    ToolExecutionResult,
    ToolPostDecision,
    ToolPreDecision,
    ToolProvider,
    ToolRenderer,
)

# ── L3 Agent / Team 入口 ──────────────────────────────────
from lca.contracts.protocols.collaboration.agent import AgentUnit

# ── 自动组队（角色库与选角契约，ADR-0042）────────
from lca.contracts.protocols.collaboration.casting import RoleLibrary, TeamCaster

# ── L3 团队编排协议 ──────────────────────────────────────
from lca.contracts.protocols.collaboration.graph_node_executor import (
    GraphNodeExecutionContext,
    GraphNodeExecutor,
    GraphNodeExecutorRegistryProtocol,
)
from lca.contracts.protocols.collaboration.orchestration import (
    MemberInvoker,
    SharedMemoryStore,
    Synthesizer,
    TeamAssembly,
    TeamStage,
    TeamStrategy,
)
from lca.contracts.protocols.collaboration.team_seam import TeamSeamFactoryProtocol
from lca.contracts.protocols.collaboration.team_unit import TeamUnit

# ── LogicAddress 6 维（ADR-0069 §二 + ADR-0074 V9）────────────────
from lca.contracts.protocols.composition.logic_address import (
    LogicAddress,
    LogicAddressScore,
    canonical_scope_of,
    declared_dim_count,
    is_complete_address,
    score_logic_address,
)
from lca.contracts.protocols.composition.relation import (
    TypedRelation,
    typed_relation_to_dict,
    typed_relations_from_iter,
)
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    DECLARATIVE_PLAN_VERSION,
    PLUGIN_SPEC_VERSION,
    ActionAuthorityPlan,
    ActionScopeAuthority,
    CapabilityBinding,
    CapabilityDeclaration,
    CognitivePhaseGraphPlan,
    ContributionRole,
    DeclarativeValidationError,
    DeltaReducer,
    EffectDispatcher,
    EffectPolicyPlan,
    JournalCommitter,
    PhaseBinding,
    PhaseContext,
    PhaseContribution,
    PhaseEdge,
    PhaseExecutor,
    PhaseInput,
    PhaseNode,
    PhaseResult,
    PlanProvenance,
    PluginConfiguration,
    PluginImplementation,
    PluginRelation,
    PluginSpec,
    PluginSpecKind,
    RelationType,
    ReplacementDecision,
    SemanticPhase,
    ValidationIssue,
    ValidationReport,
)
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    ControlEntry as DeclarativeControlEntry,
)
from lca.contracts.protocols.gate.budget_policy import BudgetPolicy

# ── 控制面单一入口（ADR-0066 + tracker §19）─────────────────────
from lca.contracts.protocols.gate.control_verdict import ControlVerdict, ControlVerdictKind

# ── GateChainComposer（ADR-0074 可定制决策门链组合）────────
from lca.contracts.protocols.gate.gate_chain_composer import GateChainComposer

# ── Lead 预算策略解析接缝 ─────────────────────────────────
from lca.contracts.protocols.gate.lead_budget_policy import LeadBudgetPolicyResolver
from lca.contracts.protocols.gate.loop_guard import LoopGuardEvaluator, LoopGuardVerdict

# ── ArtifactClosure（ADR-0074 可定制 loop exit 闭合文本）────────
from lca.contracts.protocols.journal.artifact_closure import ArtifactClosure

# ── Durable effect idempotency（ADR-0075 / full-plugin-remediation §5）────
from lca.contracts.protocols.journal.idempotency import IdempotencyClaim, IdempotencyStore

# ── 执行日志投影协议（ADR-0037 Journal-as-Truth）────────
from lca.contracts.protocols.journal.journal import JournalProjector

# ── 可观测性协议（业务层唯一发射门面）──────────────────
from lca.contracts.protocols.journal.observability import (
    ObservabilityBackend,
    Telemetry,
)

# ── ScopePlan + CompiledRunPlan（ADR-0068 §一 + ADR-0074 PR-3）──────
from lca.contracts.protocols.journal.phase_observation import (
    PhaseBudgetSnapshot,
    PhaseObserver,
    PhaseObserverContribution,
    PhaseObserverRegistry,
    PhaseStateSnapshot,
)

# ── L1 Memory 协议 ───────────────────────────────────────
from lca.contracts.protocols.memory.memory import MemorySystem, RetrievalPolicy, TemporalMemoryStore

# ── 操作技能库（与角色库平行，ADR-0048）────────────
from lca.contracts.protocols.memory.operational_skills import (
    SANDBOX_SKILL_MOUNT_PREFIX,
    SkillImporter,
    SkillImportError,
    SkillIndexEntry,
    SkillNotFoundError,
    SkillPackage,
    SkillPackageInstaller,
    SkillPackageStore,
    SkillSearchResult,
)

# ── 可选能力（无 bind/install 组装面）────────────
from lca.contracts.protocols.perceive.capabilities import HasHooks

# ── CapabilityPlan + 11 关系代数（ADR-0068 §一 + ADR-0069 §三）──────
from lca.contracts.protocols.perceive.capability_plan import (
    CapabilityPlan,
    ProviderBinding,
    capability_plan_hash,
    capability_plan_to_dict,
    relations_from_plugin,
    relations_of_kind,
    relations_to_plugin,
)

# ── L0 基础设施协议 ──────────────────────────────────────
from lca.contracts.protocols.runtime.infra import (
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
from lca.contracts.protocols.runtime.runtime import Runtime, StopPolicy
from lca.contracts.protocols.runtime.runtime_composition import (
    CheckpointStateResolver,
    CheckpointStateResolverFactory,
    DeclarativeInterpreter,
    DeclarativeInterpreterFactory,
    DeltaReducerFactory,
    EffectDispatcherFactory,
    ResultFinalizer,
    ResultFinalizerFactory,
    RuntimeFactory,
    RuntimeJournal,
    RuntimeJournalFactory,
)
from lca.contracts.protocols.runtime.runtime_lifecycle import (
    RuntimeBudgetSnapshot,
    RuntimeLifecycleEvent,
    RuntimeLifecycleEventType,
    RuntimeLifecyclePublisher,
    RuntimeLifecycleSubscriber,
    RuntimeLifecycleSubscriberContribution,
    RuntimeLifecycleSubscriberRegistry,
)
from lca.contracts.protocols.session.run_mode import (
    ModeAdapter,
    RegisteredMode,
    RunModeRegistryProtocol,
)
from lca.contracts.protocols.session.session_command_ledger import (
    ApprovalResumeDecision,
    ApprovalResumeDisposition,
    SessionCommandLedger,
)
from lca.contracts.protocols.session.session_persistence import (
    SessionPersistence,
    SessionPersistenceFactory,
)
from lca.contracts.protocols.session.session_turn import (
    SessionTurnController,
    SessionTurnControllerFactory,
    TurnAlreadyRunningError,
)
from lca.contracts.protocols.state.plan import COMPILED_RUN_PLAN_VERSION, CompiledRunPlan

# ── CommandEnvelope + RunFact (ADR-0068 §五 + ADR-0074 PR-7 V4) ─────────
# ── L2 Runtime 协议 ──────────────────────────────────────
from lca.contracts.protocols.state.reducer import Reducer
from lca.contracts.protocols.state.scope_plan import (
    BudgetCeiling,
    ScopePlan,
    scope_plan_from_iter,
    scope_plan_hash,
    scope_plan_to_dict,
)

# ── L1 认知 / Brain 协议 ─────────────────────────────────
from lca.contracts.protocols.think.cognition import (
    Brain,
    BrainFactory,
    BrainPromptCatalog,
    BrainPromptCatalogFactory,
    Critic,
    DecisionGate,
    DecisionGateAssembler,
    PerceiveHub,
    PerceiveHubAssembler,
    Reasoner,
    Sensor,
    SensorDisabledError,
    SkillRouter,
    SupportsShortcut,
)
from lca.contracts.protocols.think.cognitive_pipeline import (
    CognitiveReflectionPipeline,
    CognitiveThinkPipeline,
)

__all__ = [
    "ActionAuthorityPlan",
    "ActionHandler",
    "ActionHandlerRegistry",
    "ActionScopeAuthority",
    "AgentTransport",
    "AgentUnit",
    "ApprovalResumeDecision",
    "ApprovalResumeDisposition",
    "ArtifactClosure",
    "AttachmentIdentity",
    "Body",
    "Brain",
    "BrainFactory",
    "BrainPromptCatalog",
    "BrainPromptCatalogFactory",
    "BudgetCeiling",
    "BudgetPolicy",
    "BudgetReservation",
    "COMPILED_RUN_PLAN_VERSION",
    "CapabilityBinding",
    "CapabilityDeclaration",
    "CapabilityGrant",
    "CapabilityPlan",
    "CheckpointStateResolver",
    "CheckpointStateResolverFactory",
    "CognitivePhaseGraphPlan",
    "CognitiveReflectionPipeline",
    "CognitiveThinkPipeline",
    "CommandEnvelope",
    "CompiledRunPlan",
    "ComponentRegistryProtocol",
    "ContributionRole",
    "ControlVerdict",
    "ControlVerdictKind",
    "Critic",
    "DECLARATIVE_PLAN_VERSION",
    "DecisionGate",
    "DecisionGateAssembler",
    "DecisionRef",
    "DeclarativeControlEntry",
    "DeclarativeInterpreter",
    "DeclarativeInterpreterFactory",
    "DeclarativeValidationError",
    "DeltaReducer",
    "DeltaReducerFactory",
    "EffectCapabilities",
    "EffectDispatcher",
    "EffectDispatcherFactory",
    "EffectHandler",
    "EffectHandlerRegistry",
    "EffectPolicyPlan",
    "EnvelopeVerdict",
    "EventBus",
    "GateChainComposer",
    "GraphNodeExecutionContext",
    "GraphNodeExecutor",
    "GraphNodeExecutorRegistryProtocol",
    "HasHooks",
    "Hook",
    "HookRegistry",
    "IdempotencyClaim",
    "IdempotencyStore",
    "JournalCommitter",
    "JournalProjector",
    "LLMAdapter",
    "LeadBudgetPolicyResolver",
    "LogicAddress",
    "LogicAddressScore",
    "LoopGuardEvaluator",
    "LoopGuardVerdict",
    "MemberInvoker",
    "MemorySystem",
    "ModeAdapter",
    "NamedRegistryProtocol",
    "ObservabilityBackend",
    "OrchestrationRegistryProtocol",
    "PLUGIN_SPEC_VERSION",
    "PerceiveHub",
    "PerceiveHubAssembler",
    "PhaseBinding",
    "PhaseBudgetSnapshot",
    "PhaseContext",
    "PhaseContribution",
    "PhaseEdge",
    "PhaseExecutor",
    "PhaseInput",
    "PhaseNode",
    "PhaseObserver",
    "PhaseObserverContribution",
    "PhaseObserverRegistry",
    "PhaseResult",
    "PhaseStateSnapshot",
    "PlanProvenance",
    "PluginConfiguration",
    "PluginImplementation",
    "PluginRelation",
    "PluginSpec",
    "PluginSpecKind",
    "ProviderBinding",
    "Reasoner",
    "Reducer",
    "RegisteredMode",
    "RelationType",
    "ReplacementDecision",
    "ResultFinalizer",
    "ResultFinalizerFactory",
    "RetrievalPolicy",
    "RoleLibrary",
    "RunDelta",
    "RunFact",
    "RunModeRegistryProtocol",
    "Runtime",
    "RuntimeBudgetSnapshot",
    "RuntimeFactory",
    "RuntimeJournal",
    "RuntimeJournalFactory",
    "RuntimeLifecycleEvent",
    "RuntimeLifecycleEventType",
    "RuntimeLifecyclePublisher",
    "RuntimeLifecycleSubscriber",
    "RuntimeLifecycleSubscriberContribution",
    "RuntimeLifecycleSubscriberRegistry",
    "SANDBOX_SKILL_MOUNT_PREFIX",
    "SafeExecutor",
    "Sandbox",
    "SandboxRuntime",
    "ScopePlan",
    "SemanticPhase",
    "Sensor",
    "SensorDisabledError",
    "SessionCommandLedger",
    "SessionPersistence",
    "SessionPersistenceFactory",
    "SessionTurnController",
    "SessionTurnControllerFactory",
    "SharedMemoryStore",
    "SkillImportError",
    "SkillImporter",
    "SkillIndexEntry",
    "SkillNotFoundError",
    "SkillPackage",
    "SkillPackageInstaller",
    "SkillPackageStore",
    "SkillRouter",
    "SkillSearchResult",
    "StateStore",
    "StopPolicy",
    "SupportsShortcut",
    "Synthesizer",
    "TeamAssembly",
    "TeamCaster",
    "TeamSeamFactoryProtocol",
    "TeamStage",
    "TeamStrategy",
    "TeamUnit",
    "Telemetry",
    "TemporalMemoryStore",
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
    "TurnAlreadyRunningError",
    "TypedRelation",
    "ValidationIssue",
    "ValidationReport",
    "Verdict",
    "canonical_scope_of",
    "capability_plan_hash",
    "capability_plan_to_dict",
    "command_envelope_to_dict",
    "declared_dim_count",
    "envelope_aggregate_verdict",
    "envelope_is_authorized",
    "is_complete_address",
    "mint_envelope",
    "relations_from_plugin",
    "relations_of_kind",
    "relations_to_plugin",
    "scope_plan_from_iter",
    "scope_plan_hash",
    "scope_plan_to_dict",
    "score_logic_address",
    "typed_relation_to_dict",
    "typed_relations_from_iter",
    "warn_deprecated_envelope_constructor",
]
