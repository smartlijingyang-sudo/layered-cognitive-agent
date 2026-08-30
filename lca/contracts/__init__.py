"""LCA core contracts — typed models and protocols.

Re-export barrel: every ``from X import Y`` below is a deliberate public
re-export. ``__all__`` is derived from these imports at module load so the
contract has a single source of truth.
"""

from __future__ import annotations

import types

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
from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent, TokenUsage
from lca.contracts.models.core.memory import MemoryRecord, MemoryRelationKind, MemoryTrust
from lca.contracts.models.core.result import (
    ApprovalPendingError,
    BudgetExceededError,
    Result,
    ToolExecutionError,
)
from lca.contracts.models.core.state import AgentState, Budget, StateSnapshot
from lca.contracts.models.core.stop import StopDecision, StopReason
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
    StopPolicy,
    TransportRegistryProtocol,
)
from lca.contracts.protocols.act.action import Action, ActionRegistryProtocol
from lca.contracts.protocols.journal.spec import (
    Governance,
    TeamSpec,
    strategy_key_for_governance,
)

# Re-export barrel: every `from X import Y` above is intentional public re-export.
# ruff: noqa: F401
__all__ = sorted(
    name
    for name, value in globals().items()
    if not name.startswith("_")
    and not isinstance(value, types.ModuleType)
    and name != "annotations"
)
