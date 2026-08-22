"""Tests for recovery phase edge functionality (ADR-0075)."""

from __future__ import annotations

from lca.contracts.protocols.declarative_phase_graph import (
    CapabilityDeclaration,
    EvidenceDeclaration,
    LifecycleDeclaration,
    OwnershipDeclaration,
    PhaseBinding,
    PluginConfiguration,
    PluginImplementation,
    PluginSpec,
    PluginSpecKind,
    SemanticPhase,
    VerificationDeclaration,
)
from lca.harness.declarative.compiler import _compile_phase_edges_from_specs, _compile_phase_graph


def _make_recovery_spec() -> PluginSpec:
    """Create a recovery edge PluginSpec for testing."""
    return PluginSpec(
        api_version="lca/plugin-spec/v1",
        id="phase.edge.reflect_to_think.recovery",
        revision="1.0.0",
        kind=PluginSpecKind.PROVIDER,
        layer="L2",
        functional_group="cognitive-phase",
        implementation=PluginImplementation(
            module="lca.plugins.phase_edges.recovery",
            setup="setup",
        ),
        configuration=PluginConfiguration(
            schema="lca.plugins.phase_edges.recovery.RecoveryEdgeConfig",
            values={
                "source": "reflect.main",
                "target": "think.main",
                "when": "result.payload.admit_recovery",
                "loop": {
                    "max_iterations": 1,
                    "budget": "run.steps",
                    "terminal_predicate": "not result.payload.admit_recovery",
                },
            },
        ),
        provides=(
            CapabilityDeclaration(key="phase.edge.recovery", cardinality="one"),
        ),
        requires=(),
        effects=("none",),
        ownership=OwnershipDeclaration(
            reads=(),
            emits=(),
        ),
        lifecycle=LifecycleDeclaration(
            scopes=("run",),
            activation="static",
            disposal="auto",
        ),
        relations=(),
        evidence=EvidenceDeclaration(
            emits=("recovery.edge.provided",),
            replay="none",
        ),
        verification=VerificationDeclaration(
            test_suite="tests/declarative/test_recovery_edge.py",
            properties=("recovery_edge_contract",),
        ),
        contributes=(),
    )


def test_recovery_edge_from_spec() -> None:
    """Recovery plugin spec should produce a phase edge."""
    spec = _make_recovery_spec()

    # Create minimal phase bindings
    bindings = tuple(
        PhaseBinding(
            node_id=f"{phase.value}.main",
            semantic_phase=phase,
            executor_capability=f"phase.{phase.value}.standard",
            contributions=(),
        )
        for phase in SemanticPhase
    )

    edges = _compile_phase_edges_from_specs((spec,), {b.semantic_phase: b for b in bindings})

    assert len(edges) == 1
    edge = edges[0]
    assert edge.source == "reflect.main"
    assert edge.target == "think.main"
    assert edge.when == "result.payload.admit_recovery"
    assert edge.loop is not None
    assert edge.loop.max_iterations == 1
    assert edge.loop.budget == "run.steps"


def test_phase_graph_includes_recovery_edge() -> None:
    """Phase graph compilation should include recovery edges from specs."""
    recovery_spec = _make_recovery_spec()

    bindings = tuple(
        PhaseBinding(
            node_id=f"{phase.value}.main",
            semantic_phase=phase,
            executor_capability=f"phase.{phase.value}.standard",
            contributions=(),
        )
        for phase in SemanticPhase
    )

    graph = _compile_phase_graph(bindings, (recovery_spec,))

    # Compiler must not add a hidden standard topology.  With only this
    # provider selected, the graph contains only its declared recovery edge.
    assert len(graph.edges) == 1

    # Find recovery edge
    recovery_edges = [e for e in graph.edges if e.source == "reflect.main" and e.target == "think.main"]
    assert len(recovery_edges) == 1
    assert recovery_edges[0].when == "result.payload.admit_recovery"


def test_no_edge_without_phase_edge_capability() -> None:
    """Plugin without phase.edge.* capability should not produce edges."""
    from lca.contracts.protocols.declarative_phase_graph import (
        ContributionRole,
        PhaseContribution,
    )

    spec = PluginSpec(
        api_version="lca/plugin-spec/v1",
        id="phase.reflect.standard",
        revision="1.0.0",
        kind=PluginSpecKind.PHASE_EXECUTOR,
        layer="L2",
        functional_group="cognitive-phase",
        implementation=PluginImplementation(
            module="lca.plugins.phase_executors.reflect",
            setup="setup",
        ),
        configuration=PluginConfiguration(
            schema="lca.plugins.phase_executors.common.StandardPhaseConfig",
            values={},
        ),
        provides=(
            CapabilityDeclaration(key="phase.reflect.standard", cardinality="one"),
        ),
        requires=(),
        effects=("none",),
        ownership=OwnershipDeclaration(
            reads=(),
            emits=(),
        ),
        lifecycle=LifecycleDeclaration(
            scopes=("run",),
            activation="static",
            disposal="auto",
        ),
        relations=(),
        evidence=EvidenceDeclaration(
            emits=("recovery.edge.provided",),
            replay="none",
        ),
        verification=VerificationDeclaration(
            test_suite="tests/declarative/test_phase_graph.py",
            properties=("phase_result_contract",),
        ),
        contributes=(
            PhaseContribution(
                phase=SemanticPhase.REFLECT,
                role=ContributionRole.FINALIZE,
                executor="phase.reflect.standard",
                output="phase.reflect.result",
                order=0,
            ),
        ),
    )

    bindings = tuple(
        PhaseBinding(
            node_id=f"{phase.value}.main",
            semantic_phase=phase,
            executor_capability=f"phase.{phase.value}.standard",
            contributions=(),
        )
        for phase in SemanticPhase
    )

    edges = _compile_phase_edges_from_specs((spec,), {b.semantic_phase: b for b in bindings})
    assert len(edges) == 0


def test_recovery_edge_without_loop_guard() -> None:
    """Recovery edge can be declared without loop guard."""
    spec = PluginSpec(
        api_version="lca/plugin-spec/v1",
        id="phase.edge.custom",
        revision="1.0.0",
        kind=PluginSpecKind.PROVIDER,
        layer="L2",
        functional_group="cognitive-phase",
        implementation=PluginImplementation(
            module="lca.plugins.phase_edges.custom",
            setup="setup",
        ),
        configuration=PluginConfiguration(
            schema="lca.plugins.phase_edges.custom.CustomEdgeConfig",
            values={
                "source": "think.main",
                "target": "perceive.main",
                "when": "true",
            },
        ),
        provides=(
            CapabilityDeclaration(key="phase.edge.custom", cardinality="one"),
        ),
        requires=(),
        effects=("none",),
        ownership=OwnershipDeclaration(
            reads=(),
            emits=(),
        ),
        lifecycle=LifecycleDeclaration(
            scopes=("run",),
            activation="static",
            disposal="auto",
        ),
        relations=(),
        evidence=EvidenceDeclaration(
            emits=("recovery.edge.provided",),
            replay="none",
        ),
        verification=VerificationDeclaration(
            test_suite="tests/declarative/test_recovery_edge.py",
            properties=("custom_edge_contract",),
        ),
        contributes=(),
    )

    bindings = tuple(
        PhaseBinding(
            node_id=f"{phase.value}.main",
            semantic_phase=phase,
            executor_capability=f"phase.{phase.value}.standard",
            contributions=(),
        )
        for phase in SemanticPhase
    )

    edges = _compile_phase_edges_from_specs((spec,), {b.semantic_phase: b for b in bindings})

    assert len(edges) == 1
    edge = edges[0]
    assert edge.source == "think.main"
    assert edge.target == "perceive.main"
    assert edge.when == "true"
    assert edge.loop is None
