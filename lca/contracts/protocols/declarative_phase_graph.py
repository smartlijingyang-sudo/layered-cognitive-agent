"""ADR-0075 的声明式认知阶段图契约。

本模块只包含可序列化的数据模型、确定性校验和受限执行协议。它不认识任何
具体插件 ID、实现类、工具名称或 Profile 默认值；实现选择只能由
``PluginSpec`` 与 ``CompiledRunPlan`` 的 binding 表达。
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any, Protocol, cast, runtime_checkable

from lca.contracts.protocols.command_envelope import CommandEnvelope, RunDelta, RunFact

PLUGIN_SPEC_VERSION = "lca/plugin-spec/v1"
DECLARATIVE_PLAN_VERSION = "v2"


class DeclarativeValidationError(ValueError):
    """带稳定错误码的编译期声明式计划错误。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class SemanticPhase(str, Enum):
    """ADR-0075 允许的封闭语义阶段集合。"""

    PERCEIVE = "perceive"
    THINK = "think"
    ACT = "act"
    REFLECT = "reflect"
    REMEMBER = "remember"
    STOP = "stop"


class PluginSpecKind(str, Enum):
    SEAM = "seam"
    PROVIDER = "provider"
    PHASE_EXECUTOR = "phase-executor"
    CONTRIBUTION = "contribution"
    EFFECT_HANDLER = "effect-handler"
    OBSERVER = "observer"
    COMPOSITE = "composite"
    DRIVER = "driver"


class ContributionRole(str, Enum):
    PREPARE = "prepare"
    GOVERN = "govern"
    TRANSFORM = "transform"
    OBSERVE = "observe"
    FINALIZE = "finalize"


class RelationType(str, Enum):
    BEFORE = "before"
    AFTER = "after"
    CONTAINS = "contains"
    GOVERNS = "governs"
    OBSERVES = "observes"
    REPLACES = "replaces"
    AUGMENTS = "augments"
    CONFLICTS_WITH = "conflicts_with"
    DEPENDS_ON = "depends_on"
    SCOPED_BY = "scoped_by"
    EMITS_TO = "emits_to"


CARDINALITIES = frozenset({"one", "optional", "many", "ordered-many"})
AGGREGATIONS = frozenset({"all-allow", "deny-on-any-deny", "first-terminal", "ordered-rewrite"})
ALLOWED_EFFECTS = frozenset({"none", "tools", "memory", "network", "filesystem", "world"})


@dataclass(frozen=True, slots=True)
class CapabilityDeclaration:
    key: str
    cardinality: str = "one"
    protocol: str = "object"
    scope: str = "run"
    grant: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.key:
            raise DeclarativeValidationError("PS-001", "capability key must be non-empty")
        if self.cardinality not in CARDINALITIES:
            raise DeclarativeValidationError("PS-001", f"invalid cardinality: {self.cardinality}")
        if not self.protocol:
            raise DeclarativeValidationError("PS-001", "capability protocol must be non-empty")
        if not isinstance(self.grant, tuple):
            object.__setattr__(self, "grant", tuple(str(item) for item in self.grant))


@dataclass(frozen=True, slots=True)
class PluginImplementation:
    module: str
    setup: str = "setup"
    factory: str = "create_executor"

    def __post_init__(self) -> None:
        if not self.module:
            raise DeclarativeValidationError("PS-001", "implementation.module must be non-empty")
        if not self.setup:
            raise DeclarativeValidationError("PS-001", "implementation.setup must be non-empty")


@dataclass(frozen=True, slots=True)
class PluginConfiguration:
    schema: str
    values: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.schema:
            raise DeclarativeValidationError("PS-001", "configuration.schema must be non-empty")
        if not isinstance(self.values, Mapping):
            object.__setattr__(self, "values", dict(self.values))


@dataclass(frozen=True, slots=True)
class OwnershipDeclaration:
    reads: tuple[str, ...] = ()
    emits: tuple[str, ...] = ()
    state_mutation: str = "forbidden"

    def __post_init__(self) -> None:
        if self.state_mutation not in {"forbidden", "reducer-only"}:
            raise DeclarativeValidationError(
                "PS-001", "ownership.state_mutation must be forbidden or reducer-only"
            )
        if not isinstance(self.reads, tuple):
            object.__setattr__(self, "reads", tuple(str(item) for item in self.reads))
        if not isinstance(self.emits, tuple):
            object.__setattr__(self, "emits", tuple(str(item) for item in self.emits))


@dataclass(frozen=True, slots=True)
class LifecycleDeclaration:
    scopes: tuple[str, ...]
    activation: str
    disposal: str

    def __post_init__(self) -> None:
        if not self.scopes:
            raise DeclarativeValidationError("PS-001", "lifecycle.scopes must be non-empty")
        if not self.activation:
            raise DeclarativeValidationError("PS-001", "lifecycle.activation must be explicit")
        if not self.disposal:
            raise DeclarativeValidationError("PS-001", "lifecycle.disposal must be explicit")
        if not isinstance(self.scopes, tuple):
            object.__setattr__(self, "scopes", tuple(str(item) for item in self.scopes))


@dataclass(frozen=True, slots=True)
class EvidenceDeclaration:
    emits: tuple[str, ...]
    replay: str

    def __post_init__(self) -> None:
        if not self.replay:
            raise DeclarativeValidationError("PS-001", "evidence.replay must be explicit")
        if not isinstance(self.emits, tuple):
            object.__setattr__(self, "emits", tuple(str(item) for item in self.emits))


@dataclass(frozen=True, slots=True)
class VerificationDeclaration:
    test_suite: str
    properties: tuple[str, ...]
    fixtures: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.test_suite:
            raise DeclarativeValidationError("PS-001", "verification.test_suite must be non-empty")
        if not self.properties:
            raise DeclarativeValidationError("PS-001", "verification.properties must be non-empty")
        if not isinstance(self.properties, tuple):
            object.__setattr__(self, "properties", tuple(str(item) for item in self.properties))
        if not isinstance(self.fixtures, tuple):
            object.__setattr__(self, "fixtures", tuple(str(item) for item in self.fixtures))


@dataclass(frozen=True, slots=True)
class PhaseContribution:
    phase: SemanticPhase
    role: ContributionRole
    executor: str
    output: str
    order: int | None = None
    aggregation: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.phase, SemanticPhase):
            object.__setattr__(self, "phase", SemanticPhase(self.phase))
        if not isinstance(self.role, ContributionRole):
            object.__setattr__(self, "role", ContributionRole(self.role))
        if not self.executor:
            raise DeclarativeValidationError("PS-001", "contribution.executor must be non-empty")
        if not self.output:
            raise DeclarativeValidationError("PS-001", "contribution.output must be non-empty")
        if self.role is ContributionRole.GOVERN and self.aggregation not in AGGREGATIONS:
            raise DeclarativeValidationError(
                "PS-001", "govern contribution must declare a supported aggregation"
            )


@dataclass(frozen=True, slots=True)
class PluginRelation:
    type: RelationType
    target: str
    mode: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.type, RelationType):
            object.__setattr__(self, "type", RelationType(self.type))
        if not self.target:
            raise DeclarativeValidationError("PS-003", "relation target must be non-empty")
        if self.type is RelationType.REPLACES and self.mode not in {"exclusive", "fallback"}:
            raise DeclarativeValidationError(
                "PS-001", "replaces relation mode must be exclusive or fallback"
            )


@dataclass(frozen=True, slots=True)
class PluginSpec:
    """激活插件的唯一结构化架构事实。"""

    api_version: str
    id: str
    revision: str
    kind: PluginSpecKind
    layer: str
    functional_group: str
    implementation: PluginImplementation
    configuration: PluginConfiguration
    provides: tuple[CapabilityDeclaration, ...]
    requires: tuple[CapabilityDeclaration, ...]
    effects: tuple[str, ...]
    ownership: OwnershipDeclaration
    lifecycle: LifecycleDeclaration
    relations: tuple[PluginRelation, ...]
    evidence: EvidenceDeclaration
    verification: VerificationDeclaration
    contributes: tuple[PhaseContribution, ...] = ()

    def __post_init__(self) -> None:
        if self.api_version != PLUGIN_SPEC_VERSION:
            raise DeclarativeValidationError(
                "PS-001", f"unsupported PluginSpec apiVersion: {self.api_version}"
            )
        if not self.id or not self.revision or not self.layer or not self.functional_group:
            raise DeclarativeValidationError("PS-001", "identity fields must be non-empty")
        if not isinstance(self.kind, PluginSpecKind):
            object.__setattr__(self, "kind", PluginSpecKind(self.kind))
        for effect in self.effects:
            if effect not in ALLOWED_EFFECTS:
                raise DeclarativeValidationError("PS-006", f"unsupported effect class: {effect}")
        if not self.effects:
            raise DeclarativeValidationError("PS-006", "effects.classes must be non-empty")
        if not isinstance(self.provides, tuple):
            object.__setattr__(self, "provides", tuple(self.provides))
        if not isinstance(self.requires, tuple):
            object.__setattr__(self, "requires", tuple(self.requires))
        if not isinstance(self.relations, tuple):
            object.__setattr__(self, "relations", tuple(self.relations))
        if not isinstance(self.contributes, tuple):
            object.__setattr__(self, "contributes", tuple(self.contributes))
        kinds_requiring_contribution = {
            PluginSpecKind.CONTRIBUTION,
            PluginSpecKind.PHASE_EXECUTOR,
            PluginSpecKind.EFFECT_HANDLER,
            PluginSpecKind.OBSERVER,
        }
        if self.kind in kinds_requiring_contribution and not self.contributes:
            raise DeclarativeValidationError(
                "PS-001", f"{self.kind.value} requires an explicit contributes section"
            )


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    location: str = ""
    severity: str = "error"


@dataclass(frozen=True, slots=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(item for item in self.issues if item.severity == "error")

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(item for item in self.issues if item.severity != "error")

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def require_valid(self) -> None:
        if self.errors:
            first = self.errors[0]
            raise DeclarativeValidationError(first.code, first.message)


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
                "PG-007", "loop guard requires positive max_iterations, budget and terminal predicate"
            )


@dataclass(frozen=True, slots=True)
class PhaseNode:
    id: str
    semantic_phase: SemanticPhase
    binding: str
    max_visits: int
    terminal: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.semantic_phase, SemanticPhase):
            object.__setattr__(self, "semantic_phase", SemanticPhase(self.semantic_phase))
        if not self.id or not self.binding or self.max_visits <= 0:
            raise DeclarativeValidationError("PG-001", "phase node id, binding and positive max_visits required")


@dataclass(frozen=True, slots=True)
class PhaseEdge:
    source: str
    target: str
    when: str
    loop: LoopGuard | None = None

    def __post_init__(self) -> None:
        if not self.source or not self.target or not self.when:
            raise DeclarativeValidationError("PG-001", "phase edge source, target and predicate required")


@dataclass(frozen=True, slots=True)
class CognitivePhaseGraphPlan:
    entry: str
    nodes: tuple[PhaseNode, ...]
    edges: tuple[PhaseEdge, ...]

    def __post_init__(self) -> None:
        if not self.entry:
            raise DeclarativeValidationError("PG-001", "phase graph entry is required")
        if not isinstance(self.nodes, tuple):
            object.__setattr__(self, "nodes", tuple(self.nodes))
        if not isinstance(self.edges, tuple):
            object.__setattr__(self, "edges", tuple(self.edges))


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
            raise DeclarativeValidationError("PG-001", "phase binding node_id and executor required")
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
            raise DeclarativeValidationError("PS-006", "effect policy requires a gateway capability")
        if not self.allowed_effects:
            raise DeclarativeValidationError("PS-006", "effect policy must declare allowed effects")


@dataclass(frozen=True, slots=True)
class PlanProvenance:
    profile_path: str
    bundles: tuple[str, ...] = ()
    plugin_revisions: tuple[tuple[str, str], ...] = ()
    task_contract: str = ""
    environment: str = ""
    actor_grant: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PhaseInput:
    artifact: Any = None
    causation_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PhaseResult:
    """PhaseExecutor 的唯一标准返回值。"""

    result_kind: str
    facts: tuple[RunFact, ...] = ()
    deltas: tuple[RunDelta, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    next_hints: Mapping[str, Any] = field(default_factory=dict)
    payload: Any = None
    command_envelope: CommandEnvelope | None = None

    def __post_init__(self) -> None:
        if not self.result_kind:
            raise DeclarativeValidationError("RT-002", "PhaseResult.result_kind must be non-empty")
        if not isinstance(self.facts, tuple):
            object.__setattr__(self, "facts", tuple(self.facts))
        if not isinstance(self.deltas, tuple):
            object.__setattr__(self, "deltas", tuple(self.deltas))
        if not isinstance(self.evidence_refs, tuple):
            object.__setattr__(self, "evidence_refs", tuple(str(item) for item in self.evidence_refs))
        if not isinstance(self.next_hints, Mapping):
            object.__setattr__(self, "next_hints", dict(self.next_hints))


@runtime_checkable
class PhaseContext(Protocol):
    """插件可见的只读执行上下文；不暴露 Cordis Context。"""

    plan_ref: str
    node_ref: str
    state: Any
    journal: Any
    budget: Any
    artifacts: Mapping[str, Any]
    capabilities: Any
    tracing: Any

    def emit_fact(self, fact: RunFact) -> str: ...

    def propose_delta(self, delta: RunDelta) -> None: ...


@runtime_checkable
class PhaseExecutor(Protocol):
    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult: ...


@runtime_checkable
class EffectGateway(Protocol):
    async def execute(self, envelope: CommandEnvelope, policy: EffectPolicyPlan) -> Any: ...


@runtime_checkable
class JournalCommitter(Protocol):
    def commit_fact(self, fact: RunFact, *, plan_ref: str, node_ref: str) -> str: ...

    def commit_evidence(self, evidence_ref: str, *, plan_ref: str, node_ref: str) -> str: ...

    def commit_observation(self, observation: Any, *, plan_ref: str, node_ref: str) -> str: ...


@runtime_checkable
class DeltaReducer(Protocol):
    def apply_delta(self, state: Any, delta: RunDelta) -> Any: ...


class PluginSpecValidator:
    """纯 schema / 关系校验器；不参与插件选择。"""

    def validate(self, specs: Sequence[PluginSpec]) -> ValidationReport:
        issues: list[ValidationIssue] = []
        seen: set[str] = set()
        provided: dict[str, list[PluginSpec]] = defaultdict(list)
        ids = {spec.id for spec in specs}
        capability_keys: set[str] = set()
        for spec in specs:
            if spec.id in seen:
                issues.append(ValidationIssue("PS-001", f"duplicate plugin id: {spec.id}", spec.id))
            seen.add(spec.id)
            for offer in spec.provides:
                provided[offer.key].append(spec)
                capability_keys.add(offer.key)
            for contribution in spec.contributes:
                capability_keys.add(contribution.executor)
        for spec in specs:
            for requirement in spec.requires:
                if requirement.cardinality != "optional" and requirement.key not in provided:
                    issues.append(
                        ValidationIssue(
                            "PS-002",
                            f"required capability has no provider: {requirement.key}",
                            spec.id,
                        )
                    )
            for relation in spec.relations:
                target_known = relation.target in ids or relation.target in capability_keys
                if relation.target.startswith("phase."):
                    target_known = True
                if not target_known:
                    issues.append(
                        ValidationIssue(
                            "PS-003", f"relation target does not exist: {relation.target}", spec.id
                        )
                    )
                if relation.type is RelationType.REPLACES:
                    targets = [item for item in specs if item.id == relation.target]
                    if targets and not _protocols_compatible(spec, targets[0]):
                        issues.append(
                            ValidationIssue(
                                "PS-004",
                                f"replacement is protocol-incompatible with {relation.target}",
                                spec.id,
                            )
                        )
                if relation.type is RelationType.SCOPED_BY:
                    target_specs = [item for item in specs if item.id == relation.target]
                    if target_specs and not _grants_monotonic(spec, target_specs[0]):
                        issues.append(
                            ValidationIssue(
                                "PS-005", f"grant exceeds parent scope: {relation.target}", spec.id
                            )
                        )
            if any(effect != "none" for effect in spec.effects) and spec.kind not in {
                PluginSpecKind.EFFECT_HANDLER,
                PluginSpecKind.PHASE_EXECUTOR,
                PluginSpecKind.PROVIDER,
            }:
                issues.append(
                    ValidationIssue("PS-006", "effectful plugin kind has no gateway-compatible role", spec.id)
                )
        for capability, providers in provided.items():
            if len(providers) > 1 and any(
                offer.cardinality == "one"
                for provider in providers
                for offer in provider.provides
                if offer.key == capability
            ):
                replacing = any(
                    relation.type is RelationType.REPLACES
                    for provider in providers
                    for relation in provider.relations
                )
                if not replacing:
                    issues.append(
                        ValidationIssue(
                            "PS-002", f"capability cardinality conflict: {capability}", capability
                        )
                    )
        return ValidationReport(tuple(issues))


class PhaseGraphValidator:
    """验证语义闭合、因果约束、排序和有界重入。"""

    def validate(
        self,
        graph: CognitivePhaseGraphPlan,
        phase_bindings: Sequence[PhaseBinding],
        specs: Sequence[PluginSpec],
        effect_policy: EffectPolicyPlan,
    ) -> ValidationReport:
        issues: list[ValidationIssue] = []
        nodes = {node.id: node for node in graph.nodes}
        if graph.entry not in nodes:
            issues.append(ValidationIssue("PG-001", "graph entry does not identify a node", graph.entry))
        if len(nodes) != len(graph.nodes):
            issues.append(ValidationIssue("PG-001", "phase node ids must be unique"))
        phase_nodes: dict[SemanticPhase, list[PhaseNode]] = defaultdict(list)
        for node in graph.nodes:
            phase_nodes[node.semantic_phase].append(node)
        for phase in SemanticPhase:
            if not phase_nodes[phase]:
                issues.append(ValidationIssue("PG-001", f"missing semantic phase: {phase.value}"))
        bindings = {binding.node_id: binding for binding in phase_bindings}
        for node in graph.nodes:
            binding = bindings.get(node.id)
            if binding is None:
                issues.append(ValidationIssue("PG-001", f"node has no phase binding: {node.id}", node.id))
            elif binding.semantic_phase is not node.semantic_phase:
                issues.append(ValidationIssue("PG-001", f"binding semantic phase mismatch: {node.id}", node.id))
            elif binding.executor_capability != node.binding:
                issues.append(ValidationIssue("PG-001", f"binding executor mismatch: {node.id}", node.id))
        edge_targets: dict[str, list[PhaseEdge]] = defaultdict(list)
        reverse: dict[str, list[str]] = defaultdict(list)
        for edge in graph.edges:
            if edge.source not in nodes or edge.target not in nodes:
                issues.append(ValidationIssue("PG-001", "edge references unknown node", f"{edge.source}->{edge.target}"))
                continue
            edge_targets[edge.source].append(edge)
            reverse[edge.target].append(edge.source)
        if graph.entry in nodes:
            reachable = _reachable(graph.entry, edge_targets)
            for phase, candidates in phase_nodes.items():
                if not any(candidate.id in reachable for candidate in candidates):
                    issues.append(ValidationIssue("PG-001", f"semantic phase is unreachable: {phase.value}"))
            terminals = [node.id for node in graph.nodes if node.terminal]
            if not terminals or not any(terminal in reachable for terminal in terminals):
                issues.append(ValidationIssue("PG-006", "graph has no reachable terminal path"))
        self._validate_cycles(nodes, edge_targets, issues)
        self._validate_causality(graph, nodes, edge_targets, phase_bindings, specs, effect_policy, issues)
        self._validate_contribution_order(phase_bindings, specs, issues)
        return ValidationReport(tuple(issues))

    def _validate_cycles(
        self,
        nodes: Mapping[str, PhaseNode],
        outgoing: Mapping[str, Sequence[PhaseEdge]],
        issues: list[ValidationIssue],
    ) -> None:
        for component in _strongly_connected_components(nodes, outgoing):
            is_cycle = len(component) > 1 or any(
                edge.target == node_id for node_id in component for edge in outgoing.get(node_id, ())
            )
            if not is_cycle:
                continue
            component_set = set(component)
            cyclic_edges = [
                edge
                for node_id in component
                for edge in outgoing.get(node_id, ())
                if edge.target in component_set
            ]
            phase_rank = {phase: index for index, phase in enumerate(SemanticPhase)}
            back_edges = [
                edge
                for edge in cyclic_edges
                if phase_rank[nodes[edge.target].semantic_phase]
                <= phase_rank[nodes[edge.source].semantic_phase]
            ]
            if not back_edges or any(edge.loop is None for edge in back_edges):
                issues.append(ValidationIssue("PG-007", "cycle back-edge lacks loop guard", ",".join(sorted(component))))

    def _validate_causality(
        self,
        graph: CognitivePhaseGraphPlan,
        nodes: Mapping[str, PhaseNode],
        outgoing: Mapping[str, Sequence[PhaseEdge]],
        bindings: Sequence[PhaseBinding],
        specs: Sequence[PluginSpec],
        effect_policy: EffectPolicyPlan,
        issues: list[ValidationIssue],
    ) -> None:
        by_phase = {phase: [node.id for node in nodes.values() if node.semantic_phase is phase] for phase in SemanticPhase}
        if not _has_path_between_any(by_phase[SemanticPhase.PERCEIVE], by_phase[SemanticPhase.THINK], outgoing):
            issues.append(ValidationIssue("PG-001", "think must be causally reachable after perceive"))
        binding_by_node = {binding.node_id: binding for binding in bindings}
        offered_by_capability = {
            offer.key: spec
            for spec in specs
            for offer in spec.provides
        }
        effectful_act_nodes = []
        for node_id in by_phase[SemanticPhase.ACT]:
            binding = binding_by_node.get(node_id)
            spec = offered_by_capability.get(binding.executor_capability) if binding else None
            if spec and any(effect != "none" for effect in spec.effects):
                effectful_act_nodes.append(node_id)
        if effectful_act_nodes and not _has_path_between_any(
            by_phase[SemanticPhase.THINK], effectful_act_nodes, outgoing
        ):
            issues.append(ValidationIssue("PG-002", "effectful act lacks think/Decision predecessor"))
        if effectful_act_nodes and not effect_policy.gateway_capability:
            issues.append(ValidationIssue("PG-003", "effectful act has no EffectGateway policy"))
        if not _has_path_between_any(by_phase[SemanticPhase.REFLECT], by_phase[SemanticPhase.REMEMBER], outgoing):
            issues.append(ValidationIssue("PG-004", "remember must be reachable after reflect"))
        if not _has_path_between_any(by_phase[SemanticPhase.REMEMBER], by_phase[SemanticPhase.STOP], outgoing):
            issues.append(ValidationIssue("PG-006", "stop must be reachable after remember"))

    def _validate_contribution_order(
        self,
        bindings: Sequence[PhaseBinding],
        specs: Sequence[PluginSpec],
        issues: list[ValidationIssue],
    ) -> None:
        relation_index = {spec.id: spec for spec in specs}
        for binding in bindings:
            local = list(binding.contributions)
            transforms_or_governs = [
                item for item in local if item.role in {ContributionRole.TRANSFORM, ContributionRole.GOVERN}
            ]
            orders = [item.order for item in transforms_or_governs]
            if len(transforms_or_governs) > 1 and any(order is None for order in orders):
                issues.append(
                    ValidationIssue(
                        "PG-009", "phase-local transform/govern contributions need deterministic order", binding.node_id
                    )
                )
            declared_orders = [order for order in orders if order is not None]
            if len(declared_orders) != len(set(declared_orders)):
                issues.append(ValidationIssue("PG-009", "phase-local contribution order conflict", binding.node_id))
        # relation cycles are checked over explicit before/after targets where target IDs exist.
        adjacency: dict[str, set[str]] = defaultdict(set)
        for spec in specs:
            for relation in spec.relations:
                if relation.target not in relation_index:
                    continue
                if relation.type is RelationType.BEFORE:
                    adjacency[spec.id].add(relation.target)
                elif relation.type is RelationType.AFTER:
                    adjacency[relation.target].add(spec.id)
        if _has_directed_cycle(adjacency):
            issues.append(ValidationIssue("PG-009", "plugin relation ordering cycle"))


def canonical_json(value: Any) -> str:
    """跨进程稳定的 canonical JSON，用于 plan_hash。"""

    return json.dumps(_canonicalize(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def declarative_plan_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()[:32]


def plugin_spec_to_dict(spec: PluginSpec) -> dict[str, Any]:
    return cast("dict[str, Any]", _canonicalize(spec))


def phase_graph_to_dict(graph: CognitivePhaseGraphPlan) -> dict[str, Any]:
    return cast("dict[str, Any]", _canonicalize(graph))


def validation_report_to_dict(report: ValidationReport) -> dict[str, Any]:
    return {
        "valid": report.is_valid,
        "errors": [_canonicalize(item) for item in report.errors],
        "warnings": [_canonicalize(item) for item in report.warnings],
    }


def _canonicalize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            key: _canonicalize(item)
            for key, item in asdict(value).items()  # type: ignore[arg-type]
        }
    if isinstance(value, Mapping):
        return {str(key): _canonicalize(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_canonicalize(item) for item in value]
    return value


def _protocols_compatible(source: PluginSpec, target: PluginSpec) -> bool:
    source_protocols = {(item.key, item.protocol) for item in source.provides}
    target_protocols = {(item.key, item.protocol) for item in target.provides}
    return not target_protocols or bool(source_protocols & target_protocols)


def _grants_monotonic(child: PluginSpec, parent: PluginSpec) -> bool:
    child_grants = {grant for requirement in child.requires for grant in requirement.grant}
    parent_grants = {grant for offer in parent.provides for grant in offer.grant}
    return child_grants.issubset(parent_grants)


def _reachable(entry: str, outgoing: Mapping[str, Sequence[PhaseEdge]]) -> set[str]:
    visited: set[str] = set()
    todo: deque[str] = deque([entry])
    while todo:
        current = todo.popleft()
        if current in visited:
            continue
        visited.add(current)
        todo.extend(edge.target for edge in outgoing.get(current, ()))
    return visited


def _has_path_between_any(
    sources: Sequence[str], targets: Sequence[str], outgoing: Mapping[str, Sequence[PhaseEdge]]
) -> bool:
    target_set = set(targets)
    return any(bool(_reachable(source, outgoing) & target_set) for source in sources)


def _strongly_connected_components(
    nodes: Mapping[str, PhaseNode], outgoing: Mapping[str, Sequence[PhaseEdge]]
) -> tuple[tuple[str, ...], ...]:
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def visit(node_id: str) -> None:
        nonlocal index
        indices[node_id] = index
        lowlinks[node_id] = index
        index += 1
        stack.append(node_id)
        on_stack.add(node_id)
        for edge in outgoing.get(node_id, ()):
            target = edge.target
            if target not in nodes:
                continue
            if target not in indices:
                visit(target)
                lowlinks[node_id] = min(lowlinks[node_id], lowlinks[target])
            elif target in on_stack:
                lowlinks[node_id] = min(lowlinks[node_id], indices[target])
        if lowlinks[node_id] == indices[node_id]:
            component: list[str] = []
            while stack:
                target = stack.pop()
                on_stack.discard(target)
                component.append(target)
                if target == node_id:
                    break
            components.append(tuple(component))

    for node_id in nodes:
        if node_id not in indices:
            visit(node_id)
    return tuple(components)


def _has_directed_cycle(adjacency: Mapping[str, set[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        try:
            return any(visit(target) for target in adjacency.get(node, set()))
        finally:
            visiting.discard(node)
            visited.add(node)

    return any(visit(node) for node in adjacency)


__all__ = [
    "AGGREGATIONS",
    "ALLOWED_EFFECTS",
    "CARDINALITIES",
    "DECLARATIVE_PLAN_VERSION",
    "PLUGIN_SPEC_VERSION",
    "CapabilityBinding",
    "CapabilityDeclaration",
    "CognitivePhaseGraphPlan",
    "ContributionRole",
    "ControlEntry",
    "DeclarativeValidationError",
    "DeltaReducer",
    "EffectGateway",
    "EffectPolicyPlan",
    "EvidenceDeclaration",
    "JournalCommitter",
    "LifecycleDeclaration",
    "LoopGuard",
    "PhaseBinding",
    "PhaseContext",
    "PhaseContribution",
    "PhaseEdge",
    "PhaseExecutor",
    "PhaseGraphValidator",
    "PhaseInput",
    "PhaseNode",
    "PhaseResult",
    "PlanProvenance",
    "PluginConfiguration",
    "PluginImplementation",
    "PluginRelation",
    "PluginSpec",
    "PluginSpecKind",
    "PluginSpecValidator",
    "RelationType",
    "ReplacementDecision",
    "SemanticPhase",
    "ValidationIssue",
    "ValidationReport",
    "VerificationDeclaration",
    "canonical_json",
    "declarative_plan_hash",
    "phase_graph_to_dict",
    "plugin_spec_to_dict",
    "validation_report_to_dict",
]
