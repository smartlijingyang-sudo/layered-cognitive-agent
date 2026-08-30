"""Declarative plan validation owned by the harness.

The contracts package describes immutable data and Protocols.  This module owns
validation policy because validation depends on how a compiled plan is used by
the harness, not on the wire shape of an individual contract.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

from lca.contracts.protocols.declarative.declarative_phase_graph import (
    CognitivePhaseGraphPlan,
    ContributionRole,
    DeclarativeValidationError,
    EffectPolicyPlan,
    PhaseBinding,
    PhaseEdge,
    PhaseNode,
    PhaseResult,
    PluginSpec,
    RelationType,
    SemanticPhase,
    ValidationIssue,
    ValidationReport,
)
from lca.harness.declarative.graph_algorithms import (
    has_directed_cycle,
    has_path_between_any,
    reachable,
    strongly_connected_components,
)
from lca.harness.declarative.predicate import evaluate_restricted_predicate


class PhaseGraphValidator:
    """Validate semantic closure, causality, ordering and bounded re-entry."""

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
            issues.append(
                ValidationIssue("PG-001", "graph entry does not identify a node", graph.entry)
            )
        if len(nodes) != len(graph.nodes):
            issues.append(ValidationIssue("PG-001", "phase node ids must be unique"))
        self._validate_approval_resume_node(graph, nodes, issues)
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
                issues.append(
                    ValidationIssue("PG-001", f"node has no phase binding: {node.id}", node.id)
                )
            elif binding.semantic_phase is not node.semantic_phase:
                issues.append(
                    ValidationIssue(
                        "PG-001", f"binding semantic phase mismatch: {node.id}", node.id
                    )
                )
            elif binding.executor_capability != node.binding:
                issues.append(
                    ValidationIssue("PG-001", f"binding executor mismatch: {node.id}", node.id)
                )
        edge_targets: dict[str, list[PhaseEdge]] = defaultdict(list)
        for edge in graph.edges:
            if edge.source not in nodes or edge.target not in nodes:
                issues.append(
                    ValidationIssue(
                        "PG-001", "edge references unknown node", f"{edge.source}->{edge.target}"
                    )
                )
                continue
            edge_targets[edge.source].append(edge)
        if graph.entry in nodes:
            reachable_nodes = reachable(graph.entry, edge_targets)
            for phase, candidates in phase_nodes.items():
                if not any(candidate.id in reachable_nodes for candidate in candidates):
                    issues.append(
                        ValidationIssue("PG-001", f"semantic phase is unreachable: {phase.value}")
                    )
            terminals = [node.id for node in graph.nodes if node.terminal]
            if not terminals or not any(terminal in reachable_nodes for terminal in terminals):
                issues.append(ValidationIssue("PG-006", "graph has no reachable terminal path"))
        self._validate_cycles(nodes, edge_targets, issues)
        self._validate_execution_failure_routes(nodes, edge_targets, issues)
        self._validate_causality(
            graph, nodes, edge_targets, phase_bindings, specs, effect_policy, issues
        )
        self._validate_contribution_order(phase_bindings, specs, issues)
        return ValidationReport(tuple(issues))

    @staticmethod
    def _validate_execution_failure_routes(
        nodes: Mapping[str, PhaseNode],
        outgoing: Mapping[str, Sequence[PhaseEdge]],
        issues: list[ValidationIssue],
    ) -> None:
        """Require an error-only terminal edge for every routable exhausted phase."""

        terminals = {node.id for node in nodes.values() if node.terminal}
        for node in nodes.values():
            if node.execution_policy.on_exhausted != "route_to_stop":
                continue
            routes_error_to_terminal = any(
                edge.target in terminals and _is_phase_error_predicate(edge.when)
                for edge in outgoing.get(node.id, ())
            )
            if not routes_error_to_terminal:
                issues.append(
                    ValidationIssue(
                        "PG-010",
                        "route_to_stop phase policy requires an error-only edge to a terminal node",
                        node.id,
                    )
                )

    def _validate_approval_resume_node(
        self,
        graph: CognitivePhaseGraphPlan,
        nodes: Mapping[str, PhaseNode],
        issues: list[ValidationIssue],
    ) -> None:
        """Require approval re-entry to name a declared Think node when configured."""

        node_id = graph.approval_resume_node
        if node_id is None:
            return
        node = nodes.get(node_id)
        if node is None:
            issues.append(
                ValidationIssue("PG-001", "approval resume node does not identify a node", node_id)
            )
        elif node.semantic_phase is not SemanticPhase.THINK:
            issues.append(
                ValidationIssue("PG-001", "approval resume node must be a think node", node_id)
            )

    def _validate_cycles(
        self,
        nodes: Mapping[str, PhaseNode],
        outgoing: Mapping[str, Sequence[PhaseEdge]],
        issues: list[ValidationIssue],
    ) -> None:
        for component in strongly_connected_components(nodes, outgoing):
            is_cycle = len(component) > 1 or any(
                edge.target == node_id
                for node_id in component
                for edge in outgoing.get(node_id, ())
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
                issues.append(
                    ValidationIssue(
                        "PG-007", "cycle back-edge lacks loop guard", ",".join(sorted(component))
                    )
                )

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
        del graph
        by_phase = {
            phase: [node.id for node in nodes.values() if node.semantic_phase is phase]
            for phase in SemanticPhase
        }
        if not has_path_between_any(
            by_phase[SemanticPhase.PERCEIVE], by_phase[SemanticPhase.THINK], outgoing
        ):
            issues.append(
                ValidationIssue("PG-001", "think must be causally reachable after perceive")
            )
        binding_by_node = {binding.node_id: binding for binding in bindings}
        offered_by_capability = {offer.key: spec for spec in specs for offer in spec.provides}
        effectful_act_nodes = []
        for node_id in by_phase[SemanticPhase.ACT]:
            binding = binding_by_node.get(node_id)
            spec = offered_by_capability.get(binding.executor_capability) if binding else None
            if spec and any(effect != "none" for effect in spec.effects):
                effectful_act_nodes.append(node_id)
        if effectful_act_nodes and not has_path_between_any(
            by_phase[SemanticPhase.THINK], effectful_act_nodes, outgoing
        ):
            issues.append(
                ValidationIssue("PG-002", "effectful act lacks think/Decision predecessor")
            )
        if effectful_act_nodes and not effect_policy.gateway_capability:
            issues.append(ValidationIssue("PG-003", "effectful act has no EffectGateway policy"))
        if not has_path_between_any(
            by_phase[SemanticPhase.REFLECT], by_phase[SemanticPhase.REMEMBER], outgoing
        ):
            issues.append(ValidationIssue("PG-004", "remember must be reachable after reflect"))
        if not has_path_between_any(
            by_phase[SemanticPhase.REMEMBER], by_phase[SemanticPhase.STOP], outgoing
        ):
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
                item
                for item in local
                if item.role in {ContributionRole.TRANSFORM, ContributionRole.GOVERN}
            ]
            orders = [item.order for item in transforms_or_governs]
            if len(transforms_or_governs) > 1 and any(order is None for order in orders):
                issues.append(
                    ValidationIssue(
                        "PG-009",
                        "phase-local transform/govern contributions need deterministic order",
                        binding.node_id,
                    )
                )
            declared_orders = [order for order in orders if order is not None]
            if len(declared_orders) != len(set(declared_orders)):
                issues.append(
                    ValidationIssue(
                        "PG-009", "phase-local contribution order conflict", binding.node_id
                    )
                )
        adjacency: dict[str, set[str]] = defaultdict(set)
        for spec in specs:
            for relation in spec.relations:
                if relation.target not in relation_index:
                    continue
                if relation.type is RelationType.BEFORE:
                    adjacency[spec.id].add(relation.target)
                elif relation.type is RelationType.AFTER:
                    adjacency[relation.target].add(spec.id)
        if has_directed_cycle(adjacency):
            issues.append(ValidationIssue("PG-009", "plugin relation ordering cycle"))


def _is_phase_error_predicate(expression: str) -> bool:
    """Return whether a predicate selects phase errors while excluding normal results."""

    try:
        error_selected = evaluate_restricted_predicate(
            expression,
            result=PhaseResult(result_kind="phase_error"),
            artifacts={},
        )
        normal_selected = evaluate_restricted_predicate(
            expression,
            result=PhaseResult(result_kind="context"),
            artifacts={},
        )
    except DeclarativeValidationError:
        return False
    return error_selected and not normal_selected


__all__ = ["PhaseGraphValidator"]
