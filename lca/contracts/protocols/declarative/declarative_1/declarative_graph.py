"""声明式阶段图及其已编译计划投影的稳定数据契约。

ADR-0221: ``PhaseBinding`` / ``ControlEntry`` / ``PhaseContribution`` /
``ContributionRole`` / ``AGGREGATIONS`` are retired. Phase nodes either
own a node-level ``sub_spec_ref`` (the production path) or remain in
the schema for backward compat only — the executable plan today is a
multi-node subgraph driven by NodeExecutors, not a static
binding-to-PhaseExecutor table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
    DeclarativeValidationError,
    SemanticPhase,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_fault_tolerance import (
    PhaseExecutionPolicy,
)


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
    """A typed topology anchor in the declarative phase graph.

    ``binding`` is retained for backward-compat reading (older
    profile-bundle patches may still emit it) but the production
    execution path consumes ``sub_spec_ref`` only.
    """

    id: str
    semantic_phase: SemanticPhase
    binding: str | None = None
    max_visits: int = 1
    terminal: bool = False
    execution_policy: PhaseExecutionPolicy = field(default_factory=PhaseExecutionPolicy)
    precondition: str | None = None
    terminal_predicate: str | None = None
    sub_spec_ref: "SubgraphReference | None" = None

    def __post_init__(self) -> None:
        if not isinstance(self.semantic_phase, SemanticPhase):
            object.__setattr__(self, "semantic_phase", SemanticPhase(self.semantic_phase))
        if not self.id or self.max_visits <= 0:
            raise DeclarativeValidationError(
                "PG-001", "phase node id and positive max_visits required"
            )
        if self.precondition is not None and not str(self.precondition).strip():
            raise DeclarativeValidationError(
                "PG-007", "phase node precondition must be a non-empty name when declared"
            )
        if self.terminal_predicate is not None and not str(self.terminal_predicate).strip():
            raise DeclarativeValidationError(
                "PG-007", "phase node terminal_predicate must be a non-empty name when declared"
            )
        if self.sub_spec_ref is not None and self.sub_spec_ref.binding_edge != self.id:
            raise DeclarativeValidationError(
                "PG-004",
                f"sub_spec_ref.binding_edge {self.sub_spec_ref.binding_edge!r} "
                f"must equal node.id {self.id!r}",
            )


@dataclass(frozen=True, slots=True)
class SubgraphReference:
    """Compile-time handle from one phase edge to a subgraph plan."""

    plan_ref: str
    entry_node: str
    binding_edge: str
    return_on: str = "next"

    def __post_init__(self) -> None:
        if not self.plan_ref or not self.entry_node or not self.binding_edge:
            raise DeclarativeValidationError(
                "PG-004",
                "subgraph reference requires non-empty plan_ref, entry_node and binding_edge",
            )
        if self.return_on != "next":
            raise DeclarativeValidationError(
                "PG-004",
                f"subgraph reference return_on must be 'next', got {self.return_on!r}",
            )


@dataclass(frozen=True, slots=True)
class PhaseEdge:
    source: str
    target: str
    when: str
    loop: LoopGuard | None = None
    subgraph_ref: SubgraphReference | None = None

    def __post_init__(self) -> None:
        if not self.source or not self.target or not self.when:
            raise DeclarativeValidationError(
                "PG-001", "phase edge source, target and predicate required"
            )
        if self.subgraph_ref is not None and self.subgraph_ref.binding_edge != self.source:
            raise DeclarativeValidationError(
                "PG-004",
                f"subgraph_ref.binding_edge {self.subgraph_ref.binding_edge!r} "
                f"must equal edge.source {self.source!r}",
            )


@dataclass(frozen=True, slots=True)
class CognitivePhaseGraphPlan:
    """Compiled topology, including the declared re-entry point after approval.

    .. deprecated::
        Backward-compat only (ADR-0210 §6.3 P7 §6.5). New code uses the
        P7 region-tag mechanism (``spec.region + spec.phase`` +
        ``profile.regions.declare``) and Bundle Graph Spec v2 subgraphs.
    """

    entry: str
    nodes: tuple[PhaseNode, ...]
    edges: tuple[PhaseEdge, ...]
    approval_resume_node: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.nodes, tuple):
            object.__setattr__(self, "nodes", tuple(self.nodes))
        if not isinstance(self.edges, tuple):
            object.__setattr__(self, "edges", tuple(self.edges))
        if self.nodes and not self.entry:
            raise DeclarativeValidationError("PG-001", "phase graph entry is required")


@dataclass(frozen=True, slots=True)
class ReplacementDecision:
    target: str
    winner: str
    mode: str
    reason: str
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EffectPolicyPlan:
    """Plan-owned effect governance and privilege projection (ADR-0199 §3.1)."""

    gateway_capability: str = "effect.gateway"
    allowed_effects: tuple[str, ...] = ("none",)
    approval_required: tuple[str, ...] = ()
    idempotency_required: tuple[str, ...] = ()
    privileges: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.gateway_capability:
            raise DeclarativeValidationError(
                "PS-006", "effect policy requires a gateway capability"
            )
        if not self.allowed_effects:
            raise DeclarativeValidationError("PS-006", "effect policy must declare allowed effects")
        if not isinstance(self.privileges, tuple):
            object.__setattr__(self, "privileges", tuple(self.privileges))


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
    """Plan-owned action authority, including explicit grants for each Agent scope."""

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
    "EffectPolicyPlan",
    "LoopGuard",
    "PhaseEdge",
    "PhaseExecutionPolicy",
    "PhaseNode",
    "PlanProvenance",
    "ReplacementDecision",
    "SubgraphReference",
    "ValidationIssue",
    "ValidationReport",
    "ValidationSeverity",
]
