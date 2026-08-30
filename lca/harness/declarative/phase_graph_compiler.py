"""Compile executable phase topology from resolved declarative plugin specs.

This module turns the active phase-executor, topology, policy, and edge plugins
into a deterministic phase graph.  Concrete node identities, entry selection,
terminal behaviour, visit limits, and executor bindings are all supplied by
``phase.topology.*`` providers; the compiler validates and projects them but
never supplies a hidden workflow default.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from lca.contracts.protocols.declarative_fault_tolerance import PhaseExecutionPolicy
from lca.contracts.protocols.declarative_phase_graph import (
    CognitivePhaseGraphPlan,
    ContributionRole,
    LoopGuard,
    PhaseBinding,
    PhaseContribution,
    PhaseEdge,
    PhaseNode,
    PluginSpec,
    PluginSpecKind,
    SemanticPhase,
)


@dataclass(frozen=True, slots=True)
class PhaseGraphProjection:
    """Compiled executable bindings and their declarative phase topology."""

    phase_graph: CognitivePhaseGraphPlan
    phase_bindings: tuple[PhaseBinding, ...]


@dataclass(frozen=True, slots=True)
class _DeclaredNode:
    """Validated node data emitted by a ``phase.topology.*`` plugin."""

    id: str
    semantic_phase: SemanticPhase
    executor_capability: str
    max_visits: int
    terminal: bool
    entry: bool


def compile_phase_graph_projection(specs: tuple[PluginSpec, ...]) -> PhaseGraphProjection:
    """Compile deterministic phase bindings and edges from active plugin specs."""

    declared_nodes = _compile_declared_nodes(specs)
    bindings = _compile_phase_bindings(specs, declared_nodes)
    return PhaseGraphProjection(
        phase_graph=_compile_phase_graph(declared_nodes, bindings, specs),
        phase_bindings=bindings,
    )


def _compile_declared_nodes(specs: tuple[PluginSpec, ...]) -> tuple[_DeclaredNode, ...]:
    """Read the complete node topology from selected topology providers.

    A profile that selects phase executors without a topology provider receives
    an empty graph projection rather than compiler-injected ``*.main`` nodes.
    The outer plan compiler subsequently rejects such an incomplete run plan.
    This preserves explicit plugin ownership while keeping edge-only compiler
    tests and inspection tools useful.
    """

    nodes: list[_DeclaredNode] = []
    node_ids: set[str] = set()
    entry_count = 0
    for spec in specs:
        if not any(capability.key.startswith("phase.topology.") for capability in spec.provides):
            continue
        raw_nodes = spec.configuration.values.get("nodes", ())
        if not isinstance(raw_nodes, (list, tuple)):
            raise ValueError(f"PG-001: {spec.id} nodes must be a sequence")
        for index, raw_node in enumerate(raw_nodes):
            node = _compile_declared_node(raw_node, spec_id=spec.id, index=index)
            if node.id in node_ids:
                raise ValueError(f"PG-001: duplicate declared phase node {node.id!r}")
            node_ids.add(node.id)
            entry_count += int(node.entry)
            nodes.append(node)
    if nodes and entry_count != 1:
        raise ValueError("PG-001: declarative phase topology must declare exactly one entry node")
    return tuple(nodes)


def _compile_declared_node(raw_node: object, *, spec_id: str, index: int) -> _DeclaredNode:
    """Translate one JSON-ready plugin node declaration into a closed value."""

    if not isinstance(raw_node, Mapping):
        raise ValueError(f"PG-001: {spec_id} nodes[{index}] must be a mapping")
    node_id = raw_node.get("id")
    phase = raw_node.get("phase")
    binding = raw_node.get("binding")
    max_visits = raw_node.get("max_visits")
    terminal = raw_node.get("terminal", False)
    entry = raw_node.get("entry", False)
    if not isinstance(node_id, str) or not node_id.strip():
        raise ValueError(f"PG-001: {spec_id} nodes[{index}].id must be a non-empty string")
    if not isinstance(phase, str) or not phase.strip():
        raise ValueError(f"PG-001: {spec_id} nodes[{index}].phase must be a semantic phase")
    if not isinstance(binding, str) or not binding.strip():
        raise ValueError(f"PG-001: {spec_id} nodes[{index}].binding must be a capability key")
    if isinstance(max_visits, bool) or not isinstance(max_visits, int) or max_visits <= 0:
        raise ValueError(f"PG-001: {spec_id} nodes[{index}].max_visits must be positive")
    if type(terminal) is not bool or type(entry) is not bool:
        raise ValueError(f"PG-001: {spec_id} nodes[{index}] terminal and entry must be booleans")
    try:
        semantic_phase = SemanticPhase(phase)
    except ValueError as exc:
        raise ValueError(
            f"PG-001: {spec_id} nodes[{index}].phase is not a known semantic phase: {phase!r}"
        ) from exc
    return _DeclaredNode(
        id=node_id,
        semantic_phase=semantic_phase,
        executor_capability=binding,
        max_visits=max_visits,
        terminal=terminal,
        entry=entry,
    )


def _compile_phase_bindings(
    specs: tuple[PluginSpec, ...],
    declared_nodes: tuple[_DeclaredNode, ...],
) -> tuple[PhaseBinding, ...]:
    """Bind every declared node to a selected executor and phase contributions."""

    executor_capabilities: dict[SemanticPhase, set[str]] = defaultdict(set)
    contributions: dict[SemanticPhase, list[PhaseContribution]] = defaultdict(list)
    for spec in specs:
        for contribution in spec.contributes:
            if spec.kind is PluginSpecKind.PHASE_EXECUTOR:
                executor_capabilities[contribution.phase].add(contribution.executor)
            else:
                contributions[contribution.phase].append(contribution)

    bindings: list[PhaseBinding] = []
    for node in declared_nodes:
        available = executor_capabilities.get(node.semantic_phase, set())
        if node.executor_capability not in available:
            raise ValueError(
                "PG-001: declared phase node "
                f"{node.id!r} binds {node.executor_capability!r}, which is not supplied by an "
                f"active {node.semantic_phase.value!r} phase executor"
            )
        local = tuple(
            sorted(
                contributions.get(node.semantic_phase, ()),
                key=lambda item: (
                    _role_rank(item.role),
                    item.order if item.order is not None else -1,
                    item.executor,
                ),
            )
        )
        bindings.append(
            PhaseBinding(
                node_id=node.id,
                semantic_phase=node.semantic_phase,
                executor_capability=node.executor_capability,
                contributions=local,
            )
        )
    return tuple(bindings)


def _compile_phase_graph(
    declared_nodes: tuple[_DeclaredNode, ...],
    bindings: tuple[PhaseBinding, ...],
    specs: tuple[PluginSpec, ...],
) -> CognitivePhaseGraphPlan:
    """Project plugin-owned node metadata, policies, edges, and resume routing."""

    policies = _compile_execution_policies(bindings, specs)
    nodes = tuple(
        PhaseNode(
            id=node.id,
            semantic_phase=node.semantic_phase,
            binding=node.executor_capability,
            max_visits=node.max_visits,
            terminal=node.terminal,
            execution_policy=policies.get(node.id, PhaseExecutionPolicy()),
        )
        for node in declared_nodes
    )
    entry = next((node.id for node in declared_nodes if node.entry), "")
    return CognitivePhaseGraphPlan(
        entry=entry,
        nodes=nodes,
        edges=tuple(_compile_phase_edges_from_specs(specs)),
        approval_resume_node=_compile_approval_resume_node(specs),
    )


def _compile_execution_policies(
    bindings: tuple[PhaseBinding, ...],
    specs: tuple[PluginSpec, ...],
) -> dict[str, PhaseExecutionPolicy]:
    """Compile per-node attempt policies from selected provider plugins.

    A provider may declare a policy for one concrete node id (``think.review``)
    or for every node in a semantic phase (``think``).  Duplicate declarations
    are rejected rather than relying on plugin load order.
    """

    node_ids = {binding.node_id for binding in bindings}
    node_ids_by_phase: dict[str, tuple[str, ...]] = {
        phase.value: tuple(
            binding.node_id for binding in bindings if binding.semantic_phase is phase
        )
        for phase in SemanticPhase
    }
    policies: dict[str, PhaseExecutionPolicy] = {}
    for spec in specs:
        if not any(
            capability.key.startswith("phase.execution_policy.") for capability in spec.provides
        ):
            continue
        declared = spec.configuration.values.get("policies", {})
        if not isinstance(declared, Mapping):
            raise ValueError(f"PG-010: {spec.id} policies must be a mapping")
        for raw_node_id, raw_policy in declared.items():
            identifier = str(raw_node_id)
            targets = node_ids_by_phase.get(identifier, (identifier,))
            unknown = [node_id for node_id in targets if node_id not in node_ids]
            if not targets or unknown:
                raise ValueError(
                    f"PG-010: {spec.id} declares policy for unknown phase node {raw_node_id!r}"
                )
            for node_id in targets:
                if node_id in policies:
                    raise ValueError(f"PG-010: multiple execution policies declared for {node_id}")
                policies[node_id] = _compile_execution_policy(raw_policy, spec_id=spec.id)
    return policies


def _compile_execution_policy(raw_policy: object, *, spec_id: str) -> PhaseExecutionPolicy:
    """Translate a JSON-ready plugin configuration into the typed policy contract."""

    if not isinstance(raw_policy, Mapping):
        raise ValueError(f"PG-010: {spec_id} phase execution policy must be a mapping")
    retry_on = raw_policy.get("retry_on", ())
    if not isinstance(retry_on, (list, tuple)):
        raise ValueError(f"PG-010: {spec_id} retry_on must be a sequence")
    timeout = raw_policy.get("timeout_seconds")
    return PhaseExecutionPolicy(
        max_attempts=int(raw_policy.get("max_attempts", 1)),
        timeout_seconds=float(timeout) if timeout is not None else None,
        retry_on=tuple(str(category) for category in retry_on),
        initial_backoff_seconds=float(raw_policy.get("initial_backoff_seconds", 0.0)),
        backoff_multiplier=float(raw_policy.get("backoff_multiplier", 2.0)),
        on_exhausted=str(raw_policy.get("on_exhausted", "raise")),
    )


def _compile_approval_resume_node(specs: tuple[PluginSpec, ...]) -> str | None:
    """Read one declared approval re-entry node from phase-topology providers."""

    declared = {
        node.strip()
        for spec in specs
        if any(capability.key.startswith("phase.edge.") for capability in spec.provides)
        if isinstance(node := spec.configuration.values.get("approval_resume_node"), str)
        and node.strip()
    }
    if len(declared) > 1:
        raise ValueError(
            "PG-001: phase topology providers declare conflicting approval resume nodes"
        )
    return next(iter(declared), None)


def _compile_phase_edges_from_specs(specs: tuple[PluginSpec, ...]) -> list[PhaseEdge]:
    """Extract profile-declared edges without supplying compiler-owned topology."""

    edges: list[PhaseEdge] = []
    for spec in specs:
        if not any(capability.key.startswith("phase.edge.") for capability in spec.provides):
            continue
        declarations = _edge_declarations(spec.configuration.values)
        for declaration in declarations:
            source = str(declaration.get("source", ""))
            target = str(declaration.get("target", ""))
            when = str(declaration.get("when", "true")).lower()
            if not source or not target:
                continue
            edges.append(
                PhaseEdge(
                    source=source,
                    target=target,
                    when=when,
                    loop=_compile_loop_guard(declaration.get("loop")),
                )
            )
    return edges


def _edge_declarations(values: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """Read edge declarations through the configuration Mapping interface."""

    if not values:
        return ()
    raw_declarations = values.get("edges", (values,))
    if not isinstance(raw_declarations, (list, tuple)):
        return ()
    return tuple(item for item in raw_declarations if isinstance(item, Mapping))


def _compile_loop_guard(value: object) -> LoopGuard | None:
    if not isinstance(value, Mapping):
        return None
    return LoopGuard(
        max_iterations=int(value.get("max_iterations", 1)),
        budget=str(value.get("budget", "run.steps")),
        terminal_predicate=str(value.get("terminal_predicate", "false")),
    )


def _role_rank(role: ContributionRole) -> int:
    return {
        ContributionRole.PREPARE: 0,
        ContributionRole.TRANSFORM: 1,
        ContributionRole.GOVERN: 2,
        ContributionRole.FINALIZE: 3,
        ContributionRole.OBSERVE: 4,
    }[role]


__all__ = ["PhaseGraphProjection", "compile_phase_graph_projection"]
