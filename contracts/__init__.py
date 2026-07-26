"""LCA Framework 核心契约层 —— 所有强类型数据模型与协议接口。"""

from contracts.state import Budget, StateSnapshot, TypedState
from contracts.decision import (
    ToolCall, DelegationSpec, StructuredDecision, Observation, Reflection,
)
from contracts.memory import MemoryRecord, SkillRecord, KGTriple
from contracts.role_team import (
    RoleProfile, TeamConfig, ToolPermissionManifest, RetryPolicy, CacheConfig,
)
from contracts.lifecycle import TaskStatus, AgentCard, TeamMessage
from contracts.approval import ApprovalRequest, ApprovalDecision
from contracts.observability import TraceSpan, Event
from contracts.result import Result, ApprovalPendingError, BudgetExceededError, ToolExecutionError

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
