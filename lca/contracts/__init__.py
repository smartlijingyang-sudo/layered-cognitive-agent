"""LCA Framework 核心契约层 —— 所有强类型数据模型与协议接口。"""

from lca.contracts.action import ActionOperation, ActionRegistryProtocol
from lca.contracts.approval import ApprovalDecision, ApprovalRequest
from lca.contracts.budget import create_budget
from lca.contracts.decision import (
    DelegationSpec,
    Observation,
    Reflection,
    StructuredDecision,
    ToolCall,
)
from lca.contracts.graph import (
    ExecutionGraph,
    GraphEdge,
    GraphNode,
    GraphValidationError,
)
from lca.contracts.lifecycle import AgentCard, TaskStatus, TeamMessage
from lca.contracts.loop_judge import LoopJudge, TerminationReason, TerminationSignal
from lca.contracts.mechanisms import (
    EventBus,
    Hook,
    HookRegistry,
    NamedRegistryProtocol,
    RegistryProtocol,
)
from lca.contracts.memory import KGTriple, MemoryRecord, SkillRecord
from lca.contracts.observability import Event, TraceSpan
from lca.contracts.protocols import (
    CompletionPolicy,
    SharedMemoryStore,
    TransportRegistryProtocol,
)
from lca.contracts.result import (
    ApprovalPendingError,
    BudgetExceededError,
    Result,
    ToolExecutionError,
)
from lca.contracts.role_team import (
    CacheConfig,
    RetryPolicy,
    RoleProfile,
    TeamConfig,
    ToolPermissionManifest,
)
from lca.contracts.state import Budget, StateSnapshot, TypedState
from lca.contracts.team_progress import DelegationLedgerProtocol
from lca.contracts.types import StepOutcome, TeamAssignment, Turn

__all__ = [
    "ActionOperation",
    "ActionRegistryProtocol",
    "AgentCard",
    "ApprovalDecision",
    "ApprovalPendingError",
    "ApprovalRequest",
    "Budget",
    "BudgetExceededError",
    "CacheConfig",
    "CompletionPolicy",
    "DelegationLedgerProtocol",
    "DelegationSpec",
    "Event",
    "EventBus",
    "ExecutionGraph",
    "GraphEdge",
    "GraphNode",
    "GraphValidationError",
    "Hook",
    "HookRegistry",
    "KGTriple",
    "LoopJudge",
    "MemoryRecord",
    "NamedRegistryProtocol",
    "Observation",
    "Reflection",
    "RegistryProtocol",
    "Result",
    "RetryPolicy",
    "RoleProfile",
    "SharedMemoryStore",
    "SkillRecord",
    "StateSnapshot",
    "StepOutcome",
    "StructuredDecision",
    "TaskStatus",
    "TeamAssignment",
    "TeamConfig",
    "TeamMessage",
    "TerminationReason",
    "TerminationSignal",
    "ToolCall",
    "ToolExecutionError",
    "ToolPermissionManifest",
    "TraceSpan",
    "TransportRegistryProtocol",
    "Turn",
    "TypedState",
    "create_budget",
]
