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

# ── L1 Body / 行动执行协议 ───────────────────────────────
from lca.contracts.protocols.embodiment import Body

# ── L0 基础设施协议 ──────────────────────────────────────
from lca.contracts.protocols.infra import (
    AgentTransport,
    AttachmentIdentity,
    DshRuntime,
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

# ── L1 Memory 协议 ───────────────────────────────────────
from lca.contracts.protocols.memory import MemorySystem

# ── 可观测性协议（业务层唯一发射门面）──────────────────
from lca.contracts.protocols.observability import ObservabilityBackend, Telemetry

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

# ── L2 Runtime 协议 ──────────────────────────────────────
from lca.contracts.protocols.runtime import Runtime, StopOutcomePolicy, StopRule

# ── 工具执行管线（DSH-inspired 五阶段管线）────────────
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
    "SANDBOX_SKILL_MOUNT_PREFIX",
    "AgentTransport",
    "AgentUnit",
    "AttachmentIdentity",
    "Body",
    "Brain",
    "BrainFactory",
    "BudgetAware",
    "BudgetPolicy",
    "ComponentRegistryProtocol",
    "Critic",
    "DecisionGate",
    "DshRuntime",
    "EventBus",
    "HasHooks",
    "Hook",
    "HookRegistry",
    "JournalProjector",
    "LLMAdapter",
    "MemberInvoker",
    "MemorySystem",
    "NamedRegistryProtocol",
    "ObservabilityBackend",
    "OrchestrationRegistryProtocol",
    "PerceiveHub",
    "Reasoner",
    "RoleLibrary",
    "Runtime",
    "SafeExecutor",
    "Sandbox",
    "SandboxRuntime",
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
]
