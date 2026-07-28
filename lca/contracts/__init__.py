"""LCA Framework 核心契约层 —— 所有强类型数据模型与协议接口。"""

from lca.contracts.action import ActionHandler, ActionRegistry, ActionRegistryProtocol
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
from lca.contracts.memory import KGTriple, MemoryRecord, SkillRecord
from lca.contracts.observability import Event, TraceSpan
from lca.contracts.protocols import (
    CompletionPolicy,
    RegistryProtocol,
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
from lca.contracts.team_progress import DelegationLedger, DelegationLedgerProtocol

__all__ = [
    "ActionHandler",
    "ActionRegistry",
    "ActionRegistryProtocol",
    "AgentCard",
    "ApprovalDecision",
    "ApprovalPendingError",
    "ApprovalRequest",
    "Budget",
    "BudgetExceededError",
    "CacheConfig",
    "CompletionPolicy",
    "DelegationLedger",
    "DelegationLedgerProtocol",
    "DelegationSpec",
    "Event",
    "ExecutionGraph",
    "GraphEdge",
    "GraphNode",
    "GraphValidationError",
    "KGTriple",
    "MemoryRecord",
    "Observation",
    "Reflection",
    "RegistryProtocol",
    "Result",
    "RetryPolicy",
    "RoleProfile",
    "SharedMemoryStore",
    "SkillRecord",
    "StateSnapshot",
    "StructuredDecision",
    "TaskStatus",
    "TeamConfig",
    "TeamMessage",
    "ToolCall",
    "ToolExecutionError",
    "ToolPermissionManifest",
    "TraceSpan",
    "TransportRegistryProtocol",
    "TypedState",
    "create_budget",
]
