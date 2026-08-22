from __future__ import annotations

from dataclasses import replace

import pytest

from lca.contracts.protocols.declarative_phase_graph import (
    PhaseEdge,
    PhaseGraphValidator,
    PluginRelation,
    RelationType,
    SemanticPhase,
)
from lca.contracts.protocols.plan import compiled_run_plan_ref
from lca.harness.declarative import GenericPlanInterpreter, GraphAssembler, MappingRestrictedScope
from lca.harness.profile.plan_compiler import compile_plan
from lca.harness.profile.resolve import resolve_profile
from lca.plugins.phase_executors.common import StandardPhaseExecutor


@pytest.fixture(scope="module")
def standard_plan():
    return compile_plan(resolve_profile("profiles/web-standard.yaml"))


def test_standard_profile_has_complete_plugin_specs_and_six_phase_graph(standard_plan) -> None:
    assert standard_plan.validation_report.is_valid
    assert {binding.semantic_phase for binding in standard_plan.phase_bindings} == set(SemanticPhase)
    assert standard_plan.phase_graph is not None
    assert {node.semantic_phase for node in standard_plan.phase_graph.nodes} == set(SemanticPhase)
    assert len(standard_plan.plugin_specs) >= 6


def test_plan_hash_is_deterministic_for_identical_inputs() -> None:
    hashes = {
        compiled_run_plan_ref(compile_plan(resolve_profile("profiles/web-standard.yaml")))
        for _ in range(5)
    }
    assert len(hashes) == 1


def test_phase_executor_replacement_changes_plan_hash_without_assembler_change(standard_plan) -> None:
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
        edges=(*standard_plan.phase_graph.edges, PhaseEdge(source="stop.main", target="perceive.main", when="true")),
    )
    report = PhaseGraphValidator().validate(
        graph,
        standard_plan.phase_bindings,
        standard_plan.plugin_specs,
        standard_plan.effect_policy,
    )
    assert any(issue.code == "PG-007" for issue in report.errors)


@pytest.mark.asyncio
async def test_generic_interpreter_runs_only_from_phase_bindings(standard_plan) -> None:
    capabilities = {
        f"phase.{phase.value}.standard": StandardPhaseExecutor(phase)
        for phase in SemanticPhase
    }
    executable = GraphAssembler().assemble(standard_plan, MappingRestrictedScope(capabilities))
    result = await GenericPlanInterpreter().run(executable, state={"immutable": True})
    assert [visit.semantic_phase for visit in result.visits] == list(SemanticPhase)
    assert result.terminal_node == "stop.main"
