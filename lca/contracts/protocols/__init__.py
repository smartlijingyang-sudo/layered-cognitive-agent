"""契约协议包 —— 全量 re-export，保持 ``from lca.contracts.protocols import X`` 兼容。
子模块按层拆分（ADR-0016）：
infra / cognition / embodiment / memory / runtime / agent / orchestration
跨层机制见 ``lca.contracts.mechanisms``，跨层纯类型见 ``lca.contracts.types``。
"""

from __future__ import annotations

# ── 跨层机制（re-exported from mechanisms for convenience）──
from lca.contracts.mechanisms import (
    EventBus,
    Hook,
    HookRegistry,
    NamedRegistryProtocol,
)

# ── L3 Agent / Team 入口 ──────────────────────────────────
from lca.contracts.protocols.agent import AgentEntrypoint, TeamEntrypoint

# ── 可选能力协议（ADR-0017）──────────────────────────────
from lca.contracts.protocols.capabilities import (
    ExposesComponents,
    HookRegistryHolder,
    RosterAware,
    SharedStoreBindable,
    TransportBindable,
)

# ── L1 认知 / Brain 协议 ─────────────────────────────────
from lca.contracts.protocols.cognition import (
    BrainFactory,
    BrainStrategy,
    CandidateEvaluationPipeline,
    CompletionPolicy,
    ConflictMonitor,
    Critic,
    DecisionParser,
    PromptManager,
    Reasoner,
    SkillRouter,
    StateEvaluator,
    StatePredictor,
    SupportsCompletionGuard,
    TaskCoordinator,
    TaskDecomposer,
)

# ── L1 Body / 行动执行协议 ───────────────────────────────
from lca.contracts.protocols.embodiment import Body, FallbackPolicy

# ── L0 基础设施协议 ──────────────────────────────────────
from lca.contracts.protocols.infra import (
    AgentTransport,
    LLMAdapter,
    Observability,
    SafeExecutor,
    StateStore,
    Tool,
    ToolRegistry,
    TransportRegistryProtocol,
)

# ── L1 Memory 协议 ───────────────────────────────────────
from lca.contracts.protocols.memory import MemorySystem

# ── L3 团队编排协议 ──────────────────────────────────────
from lca.contracts.protocols.orchestration import (
    OrchestrationContext,
    OrchestrationStrategy,
    SharedMemoryStore,
    Synthesizer,
)

# ── L2 Runtime 协议 ──────────────────────────────────────
from lca.contracts.protocols.runtime import Runtime, StepOutcomePolicy

# ── 纯数据类型 ───────────────────────────────────────────
from lca.contracts.types import StepOutcome

__all__ = [
    "AgentEntrypoint",
    "AgentTransport",
    "Body",
    "BrainFactory",
    "BrainStrategy",
    "CandidateEvaluationPipeline",
    "CompletionPolicy",
    "ConflictMonitor",
    "Critic",
    "DecisionParser",
    "EventBus",
    "ExposesComponents",
    "FallbackPolicy",
    "Hook",
    "HookRegistry",
    "HookRegistryHolder",
    "LLMAdapter",
    "MemorySystem",
    "NamedRegistryProtocol",
    "Observability",
    "OrchestrationContext",
    "OrchestrationStrategy",
    "PromptManager",
    "Reasoner",
    "RosterAware",
    "Runtime",
    "SafeExecutor",
    "SharedMemoryStore",
    "SharedStoreBindable",
    "SkillRouter",
    "StateEvaluator",
    "StatePredictor",
    "StateStore",
    "StepOutcome",
    "StepOutcomePolicy",
    "SupportsCompletionGuard",
    "Synthesizer",
    "TaskCoordinator",
    "TaskDecomposer",
    "TeamEntrypoint",
    "Tool",
    "ToolRegistry",
    "TransportBindable",
    "TransportRegistryProtocol",
]
