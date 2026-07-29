"""LCA Framework 核心契约层 —— 所有强类型数据模型与协议接口。

按概念分组导出，消费方统一从 ``lca.contracts`` 获取符号。
工具模块（ids / enums / message / semantic_keys / delegation_context）
需按完整路径 import，不在此处 re-export。
"""

# ── Action 能力 ──────────────────────────────────────────
from lca.contracts.action import ActionOperation, ActionRegistryProtocol

# ── HITL 人工审批 ────────────────────────────────────────
from lca.contracts.approval import ApprovalDecision, ApprovalRequest

# ── Budget 工厂 ──────────────────────────────────────────
from lca.contracts.budget import create_budget

# ── 决策与观察 ───────────────────────────────────────────
from lca.contracts.decision import (
    DelegationSpec,
    Observation,
    Reflection,
    StructuredDecision,
    ToolCall,
)

# ── DAG 执行图 ───────────────────────────────────────────
from lca.contracts.graph import (
    ExecutionGraph,
    GraphEdge,
    GraphNode,
    GraphValidationError,
)

# ── 生命周期与通信 ───────────────────────────────────────
from lca.contracts.lifecycle import AgentCard, TaskStatus, TeamMessage

# ── 循环终止 ─────────────────────────────────────────────
from lca.contracts.loop_judge import LoopJudge, TerminationReason, TerminationSignal

# ── 跨层机制（EventBus / Hook / Registry）────────────────
from lca.contracts.mechanisms import (
    EventBus,
    Hook,
    HookRegistry,
    NamedRegistryProtocol,
    RegistryProtocol,
)

# ── 记忆 ─────────────────────────────────────────────────
from lca.contracts.memory import KGTriple, MemoryRecord, SkillRecord

# ── 可观测性 ─────────────────────────────────────────────
from lca.contracts.observability import Event, TraceSpan

# ── 协议（精选）──────────────────────────────────────────
from lca.contracts.protocols import (
    CompletionPolicy,
    SharedMemoryStore,
    TransportRegistryProtocol,
)

# ── 结果与异常 ───────────────────────────────────────────
from lca.contracts.result import (
    ApprovalPendingError,
    BudgetExceededError,
    Result,
    ToolExecutionError,
)

# ── 角色与团队配置 ───────────────────────────────────────
from lca.contracts.role_team import (
    CacheConfig,
    RetryPolicy,
    RoleProfile,
    TeamConfig,
    ToolPermissionManifest,
)

# ── 状态与预算 ───────────────────────────────────────────
from lca.contracts.state import Budget, StateSnapshot, TypedState

# ── 团队委派台账 ─────────────────────────────────────────
from lca.contracts.team_progress import DelegationLedgerProtocol

# ── 纯数据类型 ───────────────────────────────────────────
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
