"""声明式阶段图及其已编译计划投影的稳定数据契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from lca.contracts.protocols.declarative_common import (
    AGGREGATIONS,
    DeclarativeValidationError,
    SemanticPhase,
)
from lca.contracts.protocols.declarative_fault_tolerance import PhaseExecutionPolicy
from lca.contracts.protocols.declarative_plugin import PhaseContribution


class ValidationSeverity(str, Enum):
    """Severity values carried by declarative validation findings."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    location: str = ""
    severity: ValidationSeverity | str = ValidationSeverity.ERROR


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Serializable validation findings for a compiled declarative plan."""

    issues: tuple[ValidationIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class CapabilityBinding:
    capability: str
    provider: str
    cardinality: str
    scope: str = "run"
    grant: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LoopGuard:
    max_iterations: int
    budget: str
    terminal_predicate: str

    def __post_init__(self) -> None:
        if self.max_iterations <= 0 or not self.budget or not self.terminal_predicate:
            raise DeclarativeValidationError(
                "PG-007",
                "loop guard requires positive max_iterations, budget and terminal predicate",
            )


@dataclass(frozen=True, slots=True)
class PhaseNode:
    id: str
    semantic_phase: SemanticPhase
    binding: str
    max_visits: int
    terminal: bool = False
    execution_policy: PhaseExecutionPolicy = field(default_factory=PhaseExecutionPolicy)

    def __post_init__(self) -> None:
        if not isinstance(self.semantic_phase, SemanticPhase):
            object.__setattr__(self, "semantic_phase", SemanticPhase(self.semantic_phase))
        if not self.id or not self.binding or self.max_visits <= 0:
            raise DeclarativeValidationError(
                "PG-001", "phase node id, binding and positive max_visits required"
            )


@dataclass(frozen=True, slots=True)
class PhaseEdge:
    source: str
    target: str
    when: str
    loop: LoopGuard | None = None

    def __post_init__(self) -> None:
        if not self.source or not self.target or not self.when:
            raise DeclarativeValidationError(
                "PG-001", "phase edge source, target and predicate required"
            )


@dataclass(frozen=True, slots=True)
class CognitivePhaseGraphPlan:
    """Compiled topology, including the declared re-entry point after approval."""

    entry: str
    nodes: tuple[PhaseNode, ...]
    edges: tuple[PhaseEdge, ...]
    approval_resume_node: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.nodes, tuple):
            object.__setattr__(self, "nodes", tuple(self.nodes))
        if not isinstance(self.edges, tuple):
            object.__setattr__(self, "edges", tuple(self.edges))
        # An edge-only projection is useful to validate a topology provider in
        # isolation. Any executable graph, however, must own an explicit entry
        # node; the compiler must never insert one as a hidden default.
        if self.nodes and not self.entry:
            raise DeclarativeValidationError("PG-001", "phase graph entry is required")


@dataclass(frozen=True, slots=True)
class PhaseBinding:
    node_id: str
    semantic_phase: SemanticPhase
    executor_capability: str
    contributions: tuple[PhaseContribution, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.semantic_phase, SemanticPhase):
            object.__setattr__(self, "semantic_phase", SemanticPhase(self.semantic_phase))
        if not self.node_id or not self.executor_capability:
            raise DeclarativeValidationError(
                "PG-001", "phase binding node_id and executor required"
            )
        if not isinstance(self.contributions, tuple):
            object.__setattr__(self, "contributions", tuple(self.contributions))


@dataclass(frozen=True, slots=True)
class ControlEntry:
    phase: SemanticPhase
    executor_capability: str
    predicate: str
    aggregation: str
    evidence_required: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.phase, SemanticPhase):
            object.__setattr__(self, "phase", SemanticPhase(self.phase))
        if self.aggregation not in AGGREGATIONS:
            raise DeclarativeValidationError("PS-001", "control entry aggregation is invalid")


@dataclass(frozen=True, slots=True)
class ReplacementDecision:
    target: str
    winner: str
    mode: str
    reason: str
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EffectPolicyPlan:
    gateway_capability: str = "effect.gateway"
    allowed_effects: tuple[str, ...] = ("none",)
    approval_required: tuple[str, ...] = ()
    idempotency_required: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.gateway_capability:
            raise DeclarativeValidationError(
                "PS-006", "effect policy requires a gateway capability"
            )
        if not self.allowed_effects:
            raise DeclarativeValidationError("PS-006", "effect policy must declare allowed effects")


@dataclass(frozen=True, slots=True)
class ActionScopeAuthority:
    """The closed action set granted to one declared Agent role scope."""

    scope: str
    allowed_actions: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not isinstance(self.scope, str) or not self.scope:
            raise DeclarativeValidationError(
                "PS-006", "action authority scope must be a non-empty string"
            )
        object.__setattr__(
            self,
            "allowed_actions",
            frozenset(str(item) for item in self.allowed_actions),
        )


@dataclass(frozen=True, slots=True)
class ActionAuthorityPlan:
    """Plan-owned action authority, including explicit grants for each Agent scope.

    ``scope`` and ``allowed_actions`` describe the plan's primary role for
    existing consumers. ``scoped_actions`` is the complete permission surface
    selected by composition when one compiled Team plan closes a member or lead.
    A direct fixture that omits ``scoped_actions`` remains a complete one-scope
    plan rather than receiving a hidden runtime fallback.
    """

    allowed_actions: frozenset[str] = field(default_factory=frozenset)
    forbidden_actions: frozenset[str] = field(default_factory=frozenset)
    scope: str = "solo"
    scoped_actions: tuple[ActionScopeAuthority, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.scope, str) or not self.scope:
            raise DeclarativeValidationError(
                "PS-006", "action authority scope must be a non-empty string"
            )
        object.__setattr__(
            self,
            "allowed_actions",
            frozenset(str(item) for item in self.allowed_actions),
        )
        object.__setattr__(
            self,
            "forbidden_actions",
            frozenset(str(item) for item in self.forbidden_actions),
        )
        scoped_actions = tuple(self.scoped_actions)
        if not scoped_actions:
            scoped_actions = (
                ActionScopeAuthority(
                    scope=self.scope,
                    allowed_actions=self.allowed_actions,
                ),
            )
        if not all(isinstance(item, ActionScopeAuthority) for item in scoped_actions):
            raise DeclarativeValidationError(
                "PS-006", "scoped action authorities must use ActionScopeAuthority values"
            )
        scopes = tuple(item.scope for item in scoped_actions)
        if len(scopes) != len(set(scopes)):
            raise DeclarativeValidationError(
                "PS-006", "scoped action authorities must not repeat a scope"
            )
        if self.scope not in scopes:
            raise DeclarativeValidationError(
                "PS-006", "action authority primary scope must have a scoped grant"
            )
        object.__setattr__(self, "scoped_actions", scoped_actions)


@dataclass(frozen=True, slots=True)
class PlanProvenance:
    profile_path: str
    bundles: tuple[str, ...] = ()
    plugin_revisions: tuple[tuple[str, str], ...] = ()
    task_contract: str = ""
    environment: str = ""
    actor_grant: tuple[str, ...] = ()


__all__ = [
    "ActionAuthorityPlan",
    "ActionScopeAuthority",
    "CapabilityBinding",
    "CognitivePhaseGraphPlan",
    "ControlEntry",
    "EffectPolicyPlan",
    "LoopGuard",
    "PhaseBinding",
    "PhaseEdge",
    "PhaseExecutionPolicy",
    "PhaseNode",
    "PlanProvenance",
    "ReplacementDecision",
    "ValidationIssue",
    "ValidationReport",
    "ValidationSeverity",
]
