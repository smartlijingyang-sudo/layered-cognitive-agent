"""LCA core contracts — typed models and protocols."""

from lca.contracts.action import Action, ActionRegistryProtocol
from lca.contracts.approval import ApprovalDecision, ApprovalRequest
from lca.contracts.budget import create_budget
from lca.contracts.decision import (
    ActResult,
    Decision,
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
from lca.contracts.loop_judge import (
    LoopJudge,
    StopDecision,
    StopReason,
    StopRule,
    TerminationReason,
    TerminationSignal,
)
from lca.contracts.mechanisms import (
    EventBus,
    Hook,
    HookRegistry,
    NamedRegistryProtocol,
)
from lca.contracts.member_status import MemberStatus
from lca.contracts.memory import MemoryRecord
from lca.contracts.observability import Event, TraceSpan
from lca.contracts.protocols import DecisionGate, SharedMemoryStore, TransportRegistryProtocol
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
from lca.contracts.run_context import RunContext
from lca.contracts.state import AgentState, Budget, StateSnapshot, TypedState
from lca.contracts.team_progress import DelegationLedgerProtocol
from lca.contracts.types import StepOutcome, Turn

# Transitional Action alias used by some imports
ActionOperation = Action

__all__ = [
    "ActResult",
    "Action",
    "ActionOperation",
    "ActionRegistryProtocol",
    "AgentCard",
    "AgentState",
    "ApprovalDecision",
    "ApprovalPendingError",
    "ApprovalRequest",
    "Budget",
    "BudgetExceededError",
    "CacheConfig",
    "Decision",
    "DecisionGate",
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
    "LoopJudge",
    "MemberStatus",
    "MemoryRecord",
    "NamedRegistryProtocol",
    "Observation",
    "Reflection",
    "Result",
    "RetryPolicy",
    "RoleProfile",
    "RunContext",
    "SharedMemoryStore",
    "StateSnapshot",
    "StepOutcome",
    "StopDecision",
    "StopReason",
    "StopRule",
    "StructuredDecision",
    "TaskStatus",
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
