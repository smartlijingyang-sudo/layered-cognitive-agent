from __future__ import annotations

from dataclasses import replace

import pytest

from lca.contracts.protocols.gate.control_verdict import ControlVerdict, ControlVerdictKind
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    PhaseEdge,
    PhaseInput,
    PhaseResult,
    PluginRelation,
    RelationType,
    SemanticPhase,
)
from lca.harness.declarative import GenericPlanInterpreter, GraphAssembler, MappingRestrictedScope
from lca.harness.declarative.graph.phase_graph_compiler import compile_phase_graph_projection
from lca.harness.declarative.controls.validation import (
    PhaseGraphValidator,
    is_validation_valid,
    validation_errors,
)
from lca.harness.plan import compiled_run_plan_ref
from lca.harness.profile.plan_compiler import compile_plan
from lca.harness.profile.resolve import resolve_profile
from tests.phase_executors import standard_phase_executors


@pytest.fixture(scope="module")
def standard_plan():
    return compile_plan(resolve_profile("profiles/web-standard.yaml"))


def test_standard_profile_has_complete_plugin_specs_and_six_phase_graph(standard_plan) -> None:
    assert is_validation_valid(standard_plan.validation_report)
    assert {binding.semantic_phase for binding in standard_plan.phase_bindings} == set(
        SemanticPhase
    )
    assert standard_plan.phase_graph is not None
    assert {node.semantic_phase for node in standard_plan.phase_graph.nodes} == set(SemanticPhase)
    assert standard_plan.phase_graph.approval_resume_node == "think.main"
    assert len(standard_plan.plugin_specs) >= 6


def test_phase_graph_projection_is_directly_testable_from_plugin_specs(standard_plan) -> None:
    """Topology compilation is a dedicated seam, not implicit compiler work."""

    projection = compile_phase_graph_projection(standard_plan.plugin_specs)

    assert projection.phase_bindings == standard_plan.phase_bindings
    assert projection.phase_graph == standard_plan.phase_graph
    assert {node.semantic_phase for node in projection.phase_graph.nodes} == set(SemanticPhase)
    assert projection.phase_graph.entry == "perceive.main"


def test_phase_topology_plugin_controls_node_identity_and_metadata(standard_plan) -> None:
    """Changing only the topology plugin changes the executable node projection."""

    topology = next(
        item for item in standard_plan.plugin_specs if item.id == "phase.topology.standard"
    )
    edges = next(item for item in standard_plan.plugin_specs if item.id == "phase.edge.standard")
    renamed = {"perceive.main": "perceive.ingress"}
    nodes = [dict(node) for node in topology.configuration.values["nodes"]]
    for node in nodes:
        if node["id"] == "perceive.main":
            node.update(id="perceive.ingress", max_visits=3)

    edge_values = dict(edges.configuration.values)
    edge_values["edges"] = [
        {
            **dict(edge),
            "source": renamed.get(edge["source"], edge["source"]),
            "target": renamed.get(edge["target"], edge["target"]),
        }
        for edge in edge_values["edges"]
    ]
    customized_topology = replace(
        topology,
        configuration=replace(topology.configuration, values={"nodes": nodes}),
    )
    customized_edges = replace(
        edges,
        configuration=replace(edges.configuration, values=edge_values),
    )
    specs = tuple(
        customized_topology
        if item.id == topology.id
        else customized_edges
        if item.id == edges.id
        else item
        for item in standard_plan.plugin_specs
    )

    projection = compile_phase_graph_projection(specs)
    report = PhaseGraphValidator().validate(
        projection.phase_graph,
        projection.phase_bindings,
        specs,
        standard_plan.effect_policy,
    )

    assert is_validation_valid(report)
    assert projection.phase_graph.entry == "perceive.ingress"
    perceive = next(node for node in projection.phase_graph.nodes if node.id == "perceive.ingress")
    assert perceive.max_visits == 3
    assert perceive.semantic_phase is SemanticPhase.PERCEIVE
    assert projection.phase_bindings[0].node_id == "perceive.ingress"


def test_no_topology_provider_means_no_hidden_phase_nodes(standard_plan) -> None:
    """The graph compiler must not restore the legacy hard-coded ``*.main`` nodes."""

    specs = tuple(
        item
        for item in standard_plan.plugin_specs
        if item.id not in {"phase.topology.standard", "phase.execution_policy.resilient"}
    )
    projection = compile_phase_graph_projection(specs)

    assert projection.phase_bindings == ()
    assert projection.phase_graph.nodes == ()


def test_plan_hash_is_deterministic_for_identical_inputs() -> None:
    hashes = {
        compiled_run_plan_ref(compile_plan(resolve_profile("profiles/web-standard.yaml")))
        for _ in range(5)
    }
    assert len(hashes) == 1


def test_phase_executor_replacement_changes_plan_hash_without_assembler_change(
    standard_plan,
) -> None:
    think = next(item for item in standard_plan.plugin_specs if item.id == "phase.think.standard")
    replacement = replace(
        think,
        id="phase.think.fixture",
        revision="2.0.0",
        relations=(
            PluginRelation(
                type=RelationType.REPLACES,
                target="phase.think.standard",
                mode="exclusive",
            ),
        ),
    )
    replaced = replace(
        standard_plan,
        plugin_specs=tuple(
            replacement if item.id == think.id else item for item in standard_plan.plugin_specs
        ),
    )
    assert compiled_run_plan_ref(replaced) != compiled_run_plan_ref(standard_plan)


def test_validator_rejects_unbounded_reentry(standard_plan) -> None:
    assert standard_plan.phase_graph is not None
    graph = replace(
        standard_plan.phase_graph,
        edges=(
            *standard_plan.phase_graph.edges,
            PhaseEdge(source="stop.main", target="perceive.main", when="true"),
        ),
    )
    report = PhaseGraphValidator().validate(
        graph,
        standard_plan.phase_bindings,
        standard_plan.plugin_specs,
        standard_plan.effect_policy,
    )
    assert any(issue.code == "PG-007" for issue in validation_errors(report))


def test_validator_rejects_non_think_approval_resume_node(standard_plan) -> None:
    assert standard_plan.phase_graph is not None
    graph = replace(standard_plan.phase_graph, approval_resume_node="act.main")

    report = PhaseGraphValidator().validate(
        graph,
        standard_plan.phase_bindings,
        standard_plan.plugin_specs,
        standard_plan.effect_policy,
    )

    assert any(
        issue.code == "PG-001" and issue.location == "act.main"
        for issue in validation_errors(report)
    )


@pytest.mark.asyncio
async def test_generic_interpreter_runs_only_from_phase_bindings(standard_plan) -> None:
    capabilities = _capabilities_for(standard_plan)
    executable = GraphAssembler().assemble(standard_plan, MappingRestrictedScope(capabilities))
    assert {node.node_id: node.semantic_phase for node in executable.nodes.values()} == {
        binding.node_id: binding.semantic_phase for binding in standard_plan.phase_bindings
    }
    result = await GenericPlanInterpreter().run(executable, state={"immutable": True})
    assert [visit.semantic_phase for visit in result.visits] == list(SemanticPhase)
    assert result.terminal_node == "stop.main"


class _AllowContribution:
    async def execute(self, _context, _input: PhaseInput) -> PhaseResult:
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                plugin_id="test.allow-contribution",
                kind=ControlVerdictKind.ALLOW,
            ),
        )


def _capabilities_for(plan):
    capabilities = dict(standard_phase_executors())
    allow = _AllowContribution()
    for binding in plan.phase_bindings:
        for contribution in binding.contributions:
            capabilities[contribution.executor] = allow
    return capabilities


class _PrepareContribution:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, _context, input: PhaseInput) -> PhaseResult:
        self.calls += 1
        return PhaseResult(result_kind="context", payload={"prepared": input.artifact})


@pytest.mark.asyncio
async def test_prepare_contribution_is_resolved_and_executed(standard_plan) -> None:
    from lca.contracts.protocols.declarative.declarative_phase_graph import ContributionRole, PhaseContribution

    prepare = _PrepareContribution()
    bindings = tuple(
        replace(
            binding,
            contributions=(
                PhaseContribution(
                    phase=SemanticPhase.PERCEIVE,
                    role=ContributionRole.PREPARE,
                    executor="contribution.prepare.fixture",
                    output="prepared.context",
                    order=0,
                ),
            ),
        )
        if binding.semantic_phase is SemanticPhase.PERCEIVE
        else binding
        for binding in standard_plan.phase_bindings
    )
    plan = replace(standard_plan, phase_bindings=bindings)
    capabilities = _capabilities_for(plan)
    capabilities["contribution.prepare.fixture"] = prepare
    executable = GraphAssembler().assemble(plan, MappingRestrictedScope(capabilities))

    await GenericPlanInterpreter().run(executable, state={"immutable": True})

    assert prepare.calls == 1
