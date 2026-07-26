"""LCA Framework 核心契约层 —— 所有强类型数据模型与协议接口。"""

from lca.contracts.state import Budget, StateSnapshot, TypedState
from lca.contracts.decision import (
    ToolCall, DelegationSpec, StructuredDecision, Observation, Reflection,
)
from lca.contracts.memory import MemoryRecord, SkillRecord, KGTriple
from lca.contracts.role_team import (
    RoleProfile, TeamConfig, ToolPermissionManifest, RetryPolicy, CacheConfig,
)
from lca.contracts.lifecycle import TaskStatus, AgentCard, TeamMessage
from lca.contracts.approval import ApprovalRequest, ApprovalDecision
from lca.contracts.observability import TraceSpan, Event
from lca.contracts.result import Result, ApprovalPendingError, BudgetExceededError, ToolExecutionError

__all__ = [
    "Budget", "StateSnapshot", "TypedState",
    "ToolCall", "DelegationSpec", "StructuredDecision", "Observation", "Reflection",
    "MemoryRecord", "SkillRecord", "KGTriple",
    "RoleProfile", "TeamConfig", "ToolPermissionManifest", "RetryPolicy", "CacheConfig",
    "TaskStatus", "AgentCard", "TeamMessage",
    "ApprovalRequest", "ApprovalDecision",
    "TraceSpan", "Event",
    "Result", "ApprovalPendingError", "BudgetExceededError", "ToolExecutionError",
]
