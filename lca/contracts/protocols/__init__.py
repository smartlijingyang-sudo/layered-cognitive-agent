"""契约协议包 —— 全量 re-export，保持 ``from lca.contracts.protocols import X`` 兼容。
子模块按层拆分（ADR-0016）：
infra / cognition / embodiment / memory / runtime / agent / orchestration
跨层机制见 ``lca.contracts.mechanisms``，跨层纯类型见 ``lca.contracts.types``。
"""

from __future__ import annotations

# ── 跨层机制（re-exported from mechanisms for convenience）──
from lca.contracts.mechanisms import (
    ComponentRegistryProtocol,
    EventBus,
    Hook,
    HookRegistry,
    NamedRegistryProtocol,
)

# ── L3 Agent / Team 入口 ──────────────────────────────────
from lca.contracts.protocols.agent import (
    AgentUnit,
    BudgetAware,
    BudgetPolicy,
    TeamUnit,
)

# ── 可选能力协议（ADR-0017）──────────────────────────────
from lca.contracts.protocols.capabilities import (
    HasBrainBodyMemory,
    HasChannel,
    HasHooks,
    HasSharedMemory,
)

# ── L1 认知 / Brain 协议 ─────────────────────────────────
from lca.contracts.protocols.cognition import (
    Brain,
    BrainFactory,
    CandidateEvaluationPipeline,
    Critic,
    DecisionGate,
    DecisionParser,
    PromptManager,
    Reasoner,
    SkillRouter,
    SupportsDecisionGate,
    SupportsShortcut,
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
    SharedMemoryStore,
    Synthesizer,
    TeamContext,
    TeamProcessStrategy,
)

# ── L2 Runtime 协议 ──────────────────────────────────────
from lca.contracts.protocols.runtime import Runtime, StopOutcomePolicy

# ── 纯数据类型 ───────────────────────────────────────────
from lca.contracts.types import StopOutcome

__all__ = [
    "AgentTransport",
    "AgentUnit",
    "Body",
    "Brain",
    "BrainFactory",
    "BudgetAware",
    "BudgetPolicy",
    "CandidateEvaluationPipeline",
    "ComponentRegistryProtocol",
    "Critic",
    "DecisionGate",
    "DecisionParser",
    "EventBus",
    "FallbackPolicy",
    "HasBrainBodyMemory",
    "HasChannel",
    "HasHooks",
    "HasSharedMemory",
    "Hook",
    "HookRegistry",
    "LLMAdapter",
    "MemorySystem",
    "NamedRegistryProtocol",
    "Observability",
    "PromptManager",
    "Reasoner",
    "Runtime",
    "SafeExecutor",
    "SharedMemoryStore",
    "SkillRouter",
    "StateStore",
    "StopOutcome",
    "StopOutcomePolicy",
    "SupportsDecisionGate",
    "SupportsShortcut",
    "Synthesizer",
    "TeamContext",
    "TeamProcessStrategy",
    "TeamUnit",
    "Tool",
    "ToolRegistry",
    "TransportRegistryProtocol",
]
