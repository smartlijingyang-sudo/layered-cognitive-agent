"""契约协议包 —— 全量 re-export，保持 ``from lca.contracts.protocols import X`` 兼容。

子模块按层拆分（ADR-0016）：
infra / cognition / embodiment / memory / runtime / agent / orchestration
跨层机制见 ``lca.contracts.mechanisms``，跨层纯类型见 ``lca.contracts.types``。
"""

from __future__ import annotations

from lca.contracts.mechanisms import (
    EventBus,
    Hook,
    HookRegistry,
    NamedRegistryProtocol,
    RegistryProtocol,
)
from lca.contracts.protocols.agent import AgentEntrypoint, TeamEntrypoint
from lca.contracts.protocols.capabilities import RosterAware, SharedStoreBindable, TransportBindable
from lca.contracts.protocols.cognition import (
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
    TaskCoordinator,
    TaskDecomposer,
)
from lca.contracts.protocols.embodiment import Body, FallbackHandler, FallbackPolicy
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
from lca.contracts.protocols.memory import MemorySystem
from lca.contracts.protocols.orchestration import (
    OrchestrationContext,
    OrchestrationStrategy,
    SharedMemoryStore,
    Synthesizer,
)
from lca.contracts.protocols.runtime import Runtime, StepOutcomePolicy
from lca.contracts.types import StepOutcome

__all__ = [
    "AgentEntrypoint",
    "AgentTransport",
    "Body",
    "BrainStrategy",
    "CandidateEvaluationPipeline",
    "CompletionPolicy",
    "ConflictMonitor",
    "Critic",
    "DecisionParser",
    "EventBus",
    "FallbackHandler",
    "FallbackPolicy",
    "Hook",
    "HookRegistry",
    "LLMAdapter",
    "MemorySystem",
    "NamedRegistryProtocol",
    "Observability",
    "OrchestrationContext",
    "OrchestrationStrategy",
    "PromptManager",
    "Reasoner",
    "RegistryProtocol",
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
    "Synthesizer",
    "TaskCoordinator",
    "TaskDecomposer",
    "TeamEntrypoint",
    "Tool",
    "ToolRegistry",
    "TransportBindable",
    "TransportRegistryProtocol",
]
