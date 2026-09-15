"""Assembler-level validation for ``PhaseEdge.subgraph_ref`` (PG-004).

GraphAssembler is retired (ADR-0221 P3 / eng/retire-v1-reasoner-sandbox).
These tests exercise ``validate_subgraph_references`` directly against
duck-typed plans that expose ``phase_graph`` (the validator's only seam).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
    DeclarativeValidationError,
    SemanticPhase,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_fault_tolerance import (
    PhaseExecutionPolicy,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    CognitivePhaseGraphPlan,
    PhaseEdge,
    PhaseNode,
    SubgraphReference,
)
from lca.harness.declarative.compile.subgraph_validation import (
    validate_subgraph_references,
)


class _StubResolver:
    def __init__(self, mapping: dict[str, object] | None = None) -> None:
        self._mapping: dict[str, object] = dict(mapping or {})
        self.called: list[str] = []

    def resolve(self, plan_ref: str) -> object | None:
        self.called.append(plan_ref)
        return self._mapping.get(plan_ref)


def _make_outer_plan(*, edge: PhaseEdge) -> SimpleNamespace:
    phase_node = PhaseNode(
        id="reflect.main",
        semantic_phase=SemanticPhase.REFLECT,
        binding="phase.test.recording",
        execution_policy=PhaseExecutionPolicy(),
    )
    target_node = PhaseNode(
        id="remember.main",
        semantic_phase=SemanticPhase.REMEMBER,
        binding="phase.test.recording",
        execution_policy=PhaseExecutionPolicy(),
    )
    phase_graph = CognitivePhaseGraphPlan(
        entry=phase_node.id,
        nodes=(phase_node, target_node),
        edges=(edge,),
    )
    return SimpleNamespace(phase_graph=phase_graph)


def _make_subgraph_plan(
    *,
    entry_node: str,
    back_ref_plan: str | None,
) -> SimpleNamespace:
    inner = PhaseNode(
        id=entry_node,
        semantic_phase=SemanticPhase.REFLECT,
        binding="phase.test.recording",
        terminal=True,
        execution_policy=PhaseExecutionPolicy(),
    )
    back_edge = None
    if back_ref_plan is not None:
        back_edge = PhaseEdge(
            source=entry_node,
            target=entry_node,
            when="true",
            subgraph_ref=SubgraphReference(
                plan_ref=back_ref_plan,
                entry_node=entry_node,
                binding_edge=entry_node,
            ),
        )
    sub_graph = CognitivePhaseGraphPlan(
        entry=entry_node,
        nodes=(inner,),
        edges=(back_edge,) if back_edge is not None else (),
    )
    return SimpleNamespace(phase_graph=sub_graph)


class TestValidateSubgraphReferences:
    def test_no_subgraph_ref_edges_means_no_resolver_call(self) -> None:
        edge = PhaseEdge(source="reflect.main", target="remember.main", when="true")
        plan = _make_outer_plan(edge=edge)
        resolver = _StubResolver()
        validate_subgraph_references(plan, resolver)  # type: ignore[arg-type]
        assert resolver.called == []

    def test_valid_reference_passes_silently(self) -> None:
        edge = PhaseEdge(
            source="reflect.main",
            target="remember.main",
            when="true",
            subgraph_ref=SubgraphReference(
                plan_ref="bundles/reflect-subgraph.yaml",
                entry_node="reflect.inner_score",
                binding_edge="reflect.main",
            ),
        )
        plan = _make_outer_plan(edge=edge)
        sub_plan = _make_subgraph_plan(
            entry_node="reflect.inner_score",
            back_ref_plan="reflect.main",
        )
        resolver = _StubResolver({"bundles/reflect-subgraph.yaml": sub_plan})
        validate_subgraph_references(plan, resolver)  # type: ignore[arg-type]
        assert resolver.called == ["bundles/reflect-subgraph.yaml"]

    def test_unresolved_reference_raises_pg_004(self) -> None:
        edge = PhaseEdge(
            source="reflect.main",
            target="remember.main",
            when="true",
            subgraph_ref=SubgraphReference(
                plan_ref="does.not.exist",
                entry_node="reflect.inner_score",
                binding_edge="reflect.main",
            ),
        )
        plan = _make_outer_plan(edge=edge)
        with pytest.raises(DeclarativeValidationError) as excinfo:
            validate_subgraph_references(plan, _StubResolver())  # type: ignore[arg-type]
        assert excinfo.value.code == "PG-004"
        assert "does.not.exist" in str(excinfo.value)

    def test_missing_mutual_reference_raises_pg_004(self) -> None:
        edge = PhaseEdge(
            source="reflect.main",
            target="remember.main",
            when="true",
            subgraph_ref=SubgraphReference(
                plan_ref="bundles/reflect-subgraph.yaml",
                entry_node="reflect.inner_score",
                binding_edge="reflect.main",
            ),
        )
        plan = _make_outer_plan(edge=edge)
        sub_plan = _make_subgraph_plan(
            entry_node="reflect.inner_score",
            back_ref_plan=None,
        )
        resolver = _StubResolver({"bundles/reflect-subgraph.yaml": sub_plan})
        with pytest.raises(DeclarativeValidationError) as excinfo:
            validate_subgraph_references(plan, resolver)  # type: ignore[arg-type]
        assert excinfo.value.code == "PG-004"
        assert "reflect.main" in str(excinfo.value)


class TestGraphAssemblerRetired:
    """Production no longer reaches GraphAssembler — fail-loud on import."""

    def test_graph_assembler_unreachable_from_harness_declarative(self) -> None:
        import lca.harness.declarative as declarative

        with pytest.raises(AttributeError, match="GraphAssembler"):
            _ = declarative.GraphAssembler

    def test_graph_assembler_module_missing(self) -> None:
        with pytest.raises(ModuleNotFoundError):
            __import__("lca.harness.declarative.compile.assembler.assembler")
