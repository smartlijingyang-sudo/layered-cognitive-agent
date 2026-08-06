"""LCA core contracts — typed models and protocols."""

from lca.contracts.mechanisms import (
    ComponentRegistryProtocol,
    EventBus,
    Hook,
    HookRegistry,
    NamedRegistryProtocol,
)
from lca.contracts.mechanisms.registries import Registries
from lca.contracts.models.core.approval import ApprovalDecision, ApprovalRequest
from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.decision import (
    Decision,
    DelegationSpec,
    Observation,
    Reflection,
    ToolCall,
    Turn,
)
from lca.contracts.models.core.lifecycle import AgentCard, TaskStatus, TeamMessage
from lca.contracts.models.core.llm import LLMResponse, TokenUsage
from lca.contracts.models.core.memory import MemoryRecord
from lca.contracts.models.core.result import (
    ApprovalPendingError,
    BudgetExceededError,
    Result,
    ToolExecutionError,
)
from lca.contracts.models.core.state import AgentState, Budget, StateSnapshot
from lca.contracts.models.core.stop import (
    StopDecision,
    StopOutcome,
    StopReason,
)
from lca.contracts.models.team.delegation import DelegationResult, find_result
from lca.contracts.models.team.graph import (
    ExecutionGraph,
    GraphEdge,
    GraphNode,
    GraphValidationError,
)
from lca.contracts.models.team.member_status import MemberStatus
from lca.contracts.models.team.role_team import (
    CacheConfig,
    RetryPolicy,
    RoleProfile,
    ToolPermissionManifest,
)
from lca.contracts.models.team.run_context import RunContext
from lca.contracts.models.team.team_awareness import ConsultDuty, TeamAwareness
from lca.contracts.models.team.team_coordination import (
    Debate,
    FanOut,
    Graph,
    LeadMandate,
    PeerRelay,
    PeerSwarm,
    Pipeline,
)
from lca.contracts.protocols import (
    DecisionGate,
    SharedMemoryStore,
    StopRule,
    TransportRegistryProtocol,
)
from lca.contracts.protocols.action import Action, ActionRegistryProtocol
from lca.contracts.protocols.spec import (
    Governance,
    TeamSpec,
    strategy_key_for_governance,
)

__all__ = [
    "Action",
    "ActionRegistryProtocol",
    "AgentCard",
    "AgentState",
    "ApprovalDecision",
    "ApprovalPendingError",
    "ApprovalRequest",
    "Budget",
    "BudgetExceededError",
    "CacheConfig",
    "ComponentRegistryProtocol",
    "ConsultDuty",
    "Debate",
    "Decision",
    "DecisionGate",
    "DelegationResult",
    "DelegationSpec",
    "EventBus",
    "ExecutionGraph",
    "FanOut",
    "Governance",
    "Graph",
    "GraphEdge",
    "GraphNode",
    "GraphValidationError",
    "Hook",
    "HookRegistry",
    "LLMResponse",
    "LeadMandate",
    "MemberStatus",
    "MemoryRecord",
    "NamedRegistryProtocol",
    "Observation",
    "PeerRelay",
    "PeerSwarm",
    "Pipeline",
    "Reflection",
    "Registries",
    "Result",
    "RetryPolicy",
    "RoleProfile",
    "RunContext",
    "SharedMemoryStore",
    "StateSnapshot",
    "StopDecision",
    "StopOutcome",
    "StopReason",
    "StopRule",
    "TaskStatus",
    "TeamAwareness",
    "TeamMessage",
    "TeamSpec",
    "TokenUsage",
    "ToolCall",
    "ToolExecutionError",
    "ToolPermissionManifest",
    "TransportRegistryProtocol",
    "Turn",
    "create_budget",
    "find_result",
    "strategy_key_for_governance",
]
