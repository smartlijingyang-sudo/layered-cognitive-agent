"""契约协议包 —— 全量 re-export，保持 ``from lca.contracts.protocols import X`` 兼容。
子模块按层拆分：
infra / cognition / embodiment / memory / runtime / agent / orchestration
跨层机制见 ``lca.contracts.mechanisms``，跨层纯类型见 ``lca.contracts.models.core``。

This module is a re-export barrel: every ``from X import Y`` below is a
deliberate public re-export, not an unused import. ``__all__`` is derived
from these imports at module load so the public surface has a single source
of truth.
"""

from __future__ import annotations

# Re-export barrel: every `from X import Y` below is intentional public re-export.
# ruff: noqa: F401
import types

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
from lca.contracts.protocols.action_handler import ActionHandler, ActionHandlerRegistry

# ── L3 Agent / Team 入口 ──────────────────────────────────
from lca.contracts.protocols.agent import (
    AgentUnit,
    BudgetAware,
    BudgetPolicy,
    TeamUnit,
)

# ── ArtifactClosure（ADR-0074 可定制 loop exit 闭合文本）────────
from lca.contracts.protocols.artifact_closure import ArtifactClosure

# ── 可选能力（无 bind/install 组装面）────────────
from lca.contracts.protocols.capabilities import HasHooks

# ── CapabilityPlan + 11 关系代数（ADR-0068 §一 + ADR-0069 §三）──────
from lca.contracts.protocols.capability_plan import (
    CapabilityPlan,
    ProviderBinding,
    capability_plan_hash,
    capability_plan_to_dict,
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
from lca.contracts.protocols.cognitive_pipeline import (
    CognitiveReflectionPipeline,
    CognitiveThinkPipeline,
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
from lca.contracts.protocols.control_verdict import ControlVerdict, ControlVerdictKind
from lca.contracts.protocols.declarative_phase_graph import (
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
    EffectGateway,
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
from lca.contracts.protocols.declarative_phase_graph import (
    ControlEntry as DeclarativeControlEntry,
)

# ── EffectHandler 与 EffectHandlerRegistry（ADR-0074 / ADR-0068）──────
from lca.contracts.protocols.effect_handler import (
    EffectCapabilities,
    EffectHandler,
    EffectHandlerRegistry,
)

# ── L1 Body / 行动执行协议 ───────────────────────────────
from lca.contracts.protocols.embodiment import Body

# ── GateChainComposer（ADR-0074 可定制决策门链组合）────────
from lca.contracts.protocols.gate_chain_composer import GateChainComposer

# ── L3 团队编排协议 ──────────────────────────────────────
from lca.contracts.protocols.graph_node_executor import (
    GraphNodeExecutionContext,
    GraphNodeExecutor,
    GraphNodeExecutorRegistryProtocol,
)

# ── Durable effect idempotency（ADR-0075 / full-plugin-remediation §5）────
from lca.contracts.protocols.idempotency import IdempotencyClaim, IdempotencyStore

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

# ── Lead 预算策略解析接缝 ─────────────────────────────────
from lca.contracts.protocols.lead_budget_policy import LeadBudgetPolicyResolver

# ── LogicAddress 6 维（ADR-0069 §二 + ADR-0074 V9）────────────────
from lca.contracts.protocols.logic_address import (
    LogicAddress,
    LogicAddressScore,
    canonical_scope_of,
    declared_dim_count,
    is_complete_address,
    score_logic_address,
)
from lca.contracts.protocols.loop_guard import LoopGuardEvaluator, LoopGuardVerdict

# ── L1 Memory 协议 ───────────────────────────────────────
from lca.contracts.protocols.memory import MemorySystem, RetrievalPolicy, TemporalMemoryStore

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
    SkillPackageInstaller,
    SkillPackageStore,
    SkillSearchResult,
)
from lca.contracts.protocols.orchestration import (
    MemberInvoker,
    SharedMemoryStore,
    Synthesizer,
    TeamAssembly,
    TeamStage,
    TeamStrategy,
)

# ── ScopePlan + CompiledRunPlan（ADR-0068 §一 + ADR-0074 PR-3）──────
from lca.contracts.protocols.phase_observation import (
    PhaseBudgetSnapshot,
    PhaseObserver,
    PhaseObserverContribution,
    PhaseObserverRegistry,
    PhaseStateSnapshot,
)
from lca.contracts.protocols.plan import COMPILED_RUN_PLAN_VERSION, CompiledRunPlan

# ── CommandEnvelope + RunFact (ADR-0068 §五 + ADR-0074 PR-7 V4) ─────────
# ── L2 Runtime 协议 ──────────────────────────────────────
from lca.contracts.protocols.reducer import Reducer
from lca.contracts.protocols.relation import (
    TypedRelation,
    typed_relation_to_dict,
    typed_relations_from_iter,
)
from lca.contracts.protocols.run_mode import (
    ModeAdapter,
    RegisteredMode,
    RunModeRegistryProtocol,
)
from lca.contracts.models.core.stop import StopDecision, StopOutcome
from lca.contracts.protocols.runtime import (
    Runtime,
    StopOutcomePolicy,
    StopPolicy,
    StopRule,
)
from lca.contracts.protocols.runtime_composition import (
    CheckpointStateResolver,
    CheckpointStateResolverFactory,
    DeclarativeInterpreter,
    DeclarativeInterpreterFactory,
    DeltaReducerFactory,
    EffectGatewayFactory,
    ResultFinalizer,
    ResultFinalizerFactory,
    RuntimeFactory,
    RuntimeJournal,
    RuntimeJournalFactory,
)
from lca.contracts.protocols.runtime_lifecycle import (
    RuntimeBudgetSnapshot,
    RuntimeLifecycleEvent,
    RuntimeLifecycleEventType,
    RuntimeLifecyclePublisher,
    RuntimeLifecycleSubscriber,
    RuntimeLifecycleSubscriberContribution,
    RuntimeLifecycleSubscriberRegistry,
)
from lca.contracts.protocols.scope_plan import (
    BudgetCeiling,
    ScopePlan,
    scope_plan_from_iter,
    scope_plan_hash,
    scope_plan_to_dict,
)
from lca.contracts.protocols.session_command_ledger import (
    ApprovalResumeDecision,
    ApprovalResumeDisposition,
    SessionCommandLedger,
)
from lca.contracts.protocols.session_persistence import (
    SessionPersistence,
    SessionPersistenceFactory,
)
from lca.contracts.protocols.session_turn import (
    SessionTurnController,
    SessionTurnControllerFactory,
    TurnAlreadyRunningError,
)
from lca.contracts.protocols.team_seam import TeamSeamFactoryProtocol

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

# Public surface: every non-private, non-submodule re-export above.
# Derived from the explicit imports so the contract has a single source of truth;
# adding or removing a re-export is a one-line edit. `annotations` is injected by
# `from __future__ import annotations` and is not a deliberate re-export, so it
# is excluded explicitly.
__all__ = sorted(
    name
    for name, value in globals().items()
    if not name.startswith("_")
    and not isinstance(value, types.ModuleType)
    and name != "annotations"
)
