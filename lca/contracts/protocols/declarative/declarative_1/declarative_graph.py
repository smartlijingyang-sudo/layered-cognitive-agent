"""声明式阶段图及其已编译计划投影的稳定数据契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
    AGGREGATIONS,
    DeclarativeValidationError,
    SemanticPhase,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_fault_tolerance import (
    PhaseExecutionPolicy,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import PhaseContribution


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
    # Plan §13.11: sub_spec_ref 节点的 binding 为 None, interpreter 走子图
    # 驱动, 不进 phase executor;其他节点 binding 必填以维持 PG-001 校验。
    binding: str | None
    max_visits: int
    terminal: bool = False
    execution_policy: PhaseExecutionPolicy = field(default_factory=PhaseExecutionPolicy)
    # PR-C (ADR-0214 §6.1): PG-007 三件套 — precondition / terminal_predicate
    # 入口校验 / 出口谓词 (callable 名字, 由 harness 注册表解析, profile YAML 用字符串名引用)。
    precondition: str | None = None
    terminal_predicate: str | None = None
    # Node-level sub_spec_ref (Node Note 2026-09-09-phase-node-sub-spec-ref):
    # 把 think 节点挂成 InfoEdgeSpec 嵌套子图代理。binding_edge 必须 == node.id,
    # 与 PhaseEdge.subgraph_ref 的 PG-004 不变量对齐。优先级低于边级 subgraph_ref
    # (interpreter 进入节点时若边级已挂 sub_spec, 不重复 fork)。
    sub_spec_ref: SubgraphReference | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.semantic_phase, SemanticPhase):
            object.__setattr__(self, "semantic_phase", SemanticPhase(self.semantic_phase))
        if not self.id or self.max_visits <= 0:
            raise DeclarativeValidationError(
                "PG-001", "phase node id and positive max_visits required"
            )
        if not self.binding and self.sub_spec_ref is None:
            raise DeclarativeValidationError(
                "PG-001", "phase node requires binding or sub_spec_ref"
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
    """Compile-time handle from one phase edge to a subgraph plan.

    Binds an outer edge to a referenced plan (bundle-relative ``plan_ref``
    or absolute plan identity), declares the entry node inside that plan,
    and pins ``binding_edge`` to the outer edge id so the assembler can
    enforce the two-graph mutual-reference invariant: if plan A's edge X
    points at plan B, plan B must declare a back-reference naming X.
    """

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
        保留 Optional / backward-compat only (ADR-0210 §6.3 P7 §6.5).
        New code should NOT set ``CompiledRunPlan.phase_graph``; use the
        P7 region-tag mechanism (spec.region + spec.phase +
        profile.regions.declare) instead. See
        ``agent_lab.profile_loader.build_region_only_phase_graph`` and
        ``lca.harness.graph.execute.interpreter._resolve_phase_graph``
        for the recommended runtime path.
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
        # An edge-only projection is useful to validate a topology provider in
        # isolation. Any executable graph, however, must own an explicit entry
        # node; the compiler must never insert one as a hidden default.
        if self.nodes and not self.entry:
            raise DeclarativeValidationError("PG-001", "phase graph entry is required")


@dataclass(frozen=True, slots=True)
class PhaseBinding:
    """Phase → executor capability binding.

    .. deprecated::
        ``semantic_phase`` field is retained for backward compat only
        (ADR-0210 §6.3). New code should use the P7 region-tag
        mechanism (``spec.region`` + ``spec.phase`` + profile's
        ``regions.declare``). The ``executor_capability`` selection
        (e.g. ``phase.perceive.standard``) remains the canonical way to
        pick an executor; region labels do NOT enter the capability
        closure (P7-I-2).
    """

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
    """Plan-owned effect governance and privilege projection (ADR-0199 §3.1 + P3-06).

    ``gateway_capability``, ``allowed_effects``, ``approval_required`` and
    ``idempotency_required`` describe the Body-side enforcement shape
    compiled from ``PluginSpec.effects`` + ``effect_governance``. The new
    ``privileges`` field (ADR-0199 §3.1 fourth dimension, P3-06) carries
    the union of ``PluginContract.privileges`` declared by every active
    plugin, so the Body path can enforce I-HPC-5 (undeclared privilege
    fails setup) without a separate scan.

    Default ``privileges=()`` keeps the field backward-compatible: any code
    that constructs ``EffectPolicyPlan`` without naming it keeps working
    unchanged.
    """

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


@runtime_checkable
class SubgraphResolver(Protocol):
    """Compile-time seam that turns a ``SubgraphReference.plan_ref`` into a plan.

    Implementations are pluggable: the default (``BundleSubgraphResolver``
    in ``lca.harness.declarative.compile.subgraph_resolver``) reads
    bundle-relative paths; test doubles return hand-built plans. The
    Protocol owns no I/O so it can be substituted in unit tests without
    touching the filesystem.
    """

    def resolve(self, plan_ref: str) -> object | None:
        """Return the referenced ``CompiledRunPlan`` or ``None`` if unresolved.

        The return is annotated as ``object`` so the Protocol stays free
        of state-layer imports; concrete implementations and validators
        narrow the type via their own contracts.
        """
        ...


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
    "SubgraphReference",
    "SubgraphResolver",
    "ValidationIssue",
    "ValidationReport",
    "ValidationSeverity",
]
