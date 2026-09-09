"""Assembler-level validation for ``PhaseEdge.subgraph_ref`` (PG-004).

When a ``CompiledRunPlan`` declares an edge with a non-None
``subgraph_ref``, the assembler MUST verify at compile time:

  1. The referenced ``plan_ref`` resolves to a ``CompiledRunPlan`` whose
     ``phase_graph`` declares the named ``entry_node`` (PG-004).
  2. The referenced plan declares a back-reference edge whose
     ``subgraph_ref.plan_ref`` names the outer edge's ``source`` —
     i.e. the two-graph mutual-reference invariant (PG-004).

The validation logic itself lives in
``lca.harness.declarative.compile.subgraph_validation``; the assembler
only delegates to it after constructing a ``SubgraphResolver``. These
tests exercise the validation pass directly and via the assembler
constructor seam.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

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
    PhaseBinding,
    PhaseEdge,
    PhaseNode,
    SubgraphReference,
    ValidationReport,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    PhaseInput,
    PhaseResult,
)
from lca.contracts.protocols.state.plan import CompiledRunPlan
from lca.harness.declarative.compile.assembler.assembler import (
    GraphAssembler,
    MappingRestrictedScope,
)
from lca.harness.declarative.compile.subgraph_validation import (
    validate_subgraph_references,
)


class _RecordingExecutor:
    async def execute(self, _context: object, _input: PhaseInput) -> PhaseResult:
        return PhaseResult(result_kind="noop")


class _StubResolver:
    """Hand-built ``SubgraphResolver`` substitute for unit tests.

    Maps ``plan_ref`` → ``CompiledRunPlan | None``. Tests that don't
    expect resolution register no entries.
    """

    def __init__(self, mapping: dict[str, CompiledRunPlan] | None = None) -> None:
        self._mapping: dict[str, CompiledRunPlan] = dict(mapping or {})
        self.called: list[str] = []

    def resolve(self, plan_ref: str) -> CompiledRunPlan | None:
        self.called.append(plan_ref)
        return self._mapping.get(plan_ref)


def _make_outer_plan(*, edge: PhaseEdge) -> CompiledRunPlan:
    phase_node = PhaseNode(
        id="reflect.main",
        semantic_phase=SemanticPhase.REFLECT,
        binding="phase.test.recording",
        max_visits=4,
        execution_policy=PhaseExecutionPolicy(),
    )
    target_node = PhaseNode(
        id="remember.main",
        semantic_phase=SemanticPhase.REMEMBER,
        binding="phase.test.recording",
        max_visits=4,
        execution_policy=PhaseExecutionPolicy(),
    )
    phase_graph = CognitivePhaseGraphPlan(
        entry=phase_node.id,
        nodes=(phase_node, target_node),
        edges=(edge,),
    )
    binding = PhaseBinding(
        node_id=phase_node.id,
        semantic_phase=SemanticPhase.REFLECT,
        executor_capability="phase.test.recording",
        contributions=(),
    )
    binding_target = PhaseBinding(
        node_id=target_node.id,
        semantic_phase=SemanticPhase.REMEMBER,
        executor_capability="phase.test.recording",
        contributions=(),
    )
    return CompiledRunPlan(
        profile_path="test://subgraph-ref-validation",
        capability=cast(
            "Any",
            SimpleNamespace(profile_path="test://subgraph-ref-validation"),
        ),
        scope=cast(
            "Any",
            SimpleNamespace(profile_path="test://subgraph-ref-validation"),
        ),
        phase_graph=phase_graph,
        phase_bindings=(binding, binding_target),
        validation_report=ValidationReport(issues=()),
    )


def _make_subgraph_plan(
    *,
    entry_node: str,
    back_ref_plan: str | None,
) -> CompiledRunPlan:
    """Build a tiny subgraph plan with the requested entry node.

    If ``back_ref_plan`` is non-None, the subgraph declares one edge
    whose ``subgraph_ref.plan_ref`` equals that value (the
    mutual-reference back-edge).
    """
    inner = PhaseNode(
        id=entry_node,
        semantic_phase=SemanticPhase.REFLECT,
        binding="phase.test.recording",
        max_visits=4,
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
    sub_binding = PhaseBinding(
        node_id=entry_node,
        semantic_phase=SemanticPhase.REFLECT,
        executor_capability="phase.test.recording",
        contributions=(),
    )
    return CompiledRunPlan(
        profile_path="sub://reflect-subgraph-test",
        capability=cast("Any", SimpleNamespace(profile_path="sub://reflect-subgraph-test")),
        scope=cast("Any", SimpleNamespace(profile_path="sub://reflect-subgraph-test")),
        phase_graph=sub_graph,
        phase_bindings=(sub_binding,),
        validation_report=ValidationReport(issues=()),
    )


class TestValidateSubgraphReferences:
    """Direct tests for the ``validate_subgraph_references`` function."""

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

    def test_unresolved_plan_ref_raises_pg_004(self) -> None:
        edge = PhaseEdge(
            source="reflect.main",
            target="remember.main",
            when="true",
            subgraph_ref=SubgraphReference(
                plan_ref="does/not/exist.yaml",
                entry_node="reflect.inner_score",
                binding_edge="reflect.main",
            ),
        )
        plan = _make_outer_plan(edge=edge)
        resolver = _StubResolver()  # empty mapping

        with pytest.raises(DeclarativeValidationError) as excinfo:
            validate_subgraph_references(plan, resolver)  # type: ignore[arg-type]
        assert excinfo.value.code == "PG-004"
        assert "does/not/exist.yaml" in str(excinfo.value)

    def test_entry_node_missing_from_subgraph_raises_pg_004(self) -> None:
        edge = PhaseEdge(
            source="reflect.main",
            target="remember.main",
            when="true",
            subgraph_ref=SubgraphReference(
                plan_ref="bundles/reflect-subgraph.yaml",
                entry_node="does.not.exist",
                binding_edge="reflect.main",
            ),
        )
        plan = _make_outer_plan(edge=edge)
        sub_plan = _make_subgraph_plan(
            entry_node="reflect.inner_score",
            back_ref_plan="reflect.main",
        )
        resolver = _StubResolver({"bundles/reflect-subgraph.yaml": sub_plan})

        with pytest.raises(DeclarativeValidationError) as excinfo:
            validate_subgraph_references(plan, resolver)  # type: ignore[arg-type]
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


class TestGraphAssemblerSubgraphWiring:
    """The assembler delegates to the validator when a resolver is set."""

    def _assemble(self, plan: CompiledRunPlan, resolver: object | None) -> None:
        GraphAssembler(subgraph_resolver=resolver).assemble(
            plan,
            MappingRestrictedScope(capabilities={"phase.test.recording": _RecordingExecutor()}),
        )

    def test_no_resolver_skips_subgraph_validation(self) -> None:
        edge = PhaseEdge(source="reflect.main", target="remember.main", when="true")
        plan = _make_outer_plan(edge=edge)
        # No resolver wired → validation pass is skipped. Existing
        # behavior preserved for plans without subgraph refs.
        self._assemble(plan, resolver=None)

    def test_resolver_invoked_when_subgraph_ref_present(self) -> None:
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

        self._assemble(plan, resolver=resolver)

        assert resolver.called == ["bundles/reflect-subgraph.yaml"]

    def test_unresolved_reference_raises_pg_004_from_assembler(self) -> None:
        edge = PhaseEdge(
            source="reflect.main",
            target="remember.main",
            when="true",
            subgraph_ref=SubgraphReference(
                plan_ref="does/not/exist.yaml",
                entry_node="reflect.inner_score",
                binding_edge="reflect.main",
            ),
        )
        plan = _make_outer_plan(edge=edge)
        resolver = _StubResolver()

        with pytest.raises(DeclarativeValidationError) as excinfo:
            self._assemble(plan, resolver=resolver)
        assert excinfo.value.code == "PG-004"
        assert "does/not/exist.yaml" in str(excinfo.value)
