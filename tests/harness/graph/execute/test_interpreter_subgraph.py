"""Interpreter-level tests for ``PhaseEdge.subgraph_ref`` recursion.

The interpreter handles a ``subgraph_ref`` on an outgoing edge by:
  1. Resolving the referenced plan via ``subgraph_resolver``.
  2. Turning it into an ``ExecutablePlan`` via
     ``subgraph_executable_factory`` (the seam that keeps the
     interpreter I/O-free).
  3. Driving the subgraph with a fresh ``PhaseTraversal`` and merging
     the resulting ``state`` back into the outer drive.
  4. Capping recursion at ``_MAX_SUBGRAPH_DEPTH`` (PG-005).

These tests exercise ``_drive_subgraph`` directly so the recursion
contract is independent of the surrounding ``_drive`` orchestration.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from lca.contracts.models.core.state.state import AgentState, Budget
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
    ExecutableNode,
    ExecutablePlan,
)
from lca.harness.graph.execute.interpreter import (
    MAX_SUBGRAPH_DEPTH,
    GenericPlanInterpreter,
)


class _RecordingExecutor:
    async def execute(self, _context: object, _input: PhaseInput) -> PhaseResult:
        return PhaseResult(result_kind="noop")


def _state() -> AgentState:
    return AgentState(trace_id="trace:test", task="test", budget=Budget())


def _outer_edge_with_ref() -> PhaseEdge:
    return PhaseEdge(
        source="reflect.main",
        target="remember.main",
        when="true",
        subgraph_ref=SubgraphReference(
            plan_ref="bundles/reflect-subgraph.yaml",
            entry_node="reflect.inner_score",
            binding_edge="reflect.main",
        ),
    )


def _sub_plan() -> CompiledRunPlan:
    node = PhaseNode(
        id="reflect.inner_score",
        semantic_phase=SemanticPhase.REFLECT,
        binding="phase.test.recording",
        max_visits=4,
        terminal=True,
        execution_policy=PhaseExecutionPolicy(),
    )
    graph = CognitivePhaseGraphPlan(
        entry=node.id,
        nodes=(node,),
        edges=(),
    )
    binding = PhaseBinding(
        node_id=node.id,
        semantic_phase=SemanticPhase.REFLECT,
        executor_capability="phase.test.recording",
        contributions=(),
    )
    return CompiledRunPlan(
        profile_path="sub://reflect-subgraph-test",
        capability=cast("Any", SimpleNamespace(profile_path="sub://reflect-subgraph-test")),
        scope=cast("Any", SimpleNamespace(profile_path="sub://reflect-subgraph-test")),
        phase_graph=graph,
        phase_bindings=(binding,),
        validation_report=ValidationReport(issues=()),
    )


def _executable_for(plan: CompiledRunPlan) -> ExecutablePlan:
    nodes = {
        node.id: ExecutableNode(
            node_id=node.id,
            semantic_phase=SemanticPhase.REFLECT,
            executor_capability="phase.test.recording",
            executor=_RecordingExecutor(),
            contributions=(),
            execution_policy=PhaseExecutionPolicy(),
        )
        for node in (plan.phase_graph.nodes if plan.phase_graph else ())
    }
    return ExecutablePlan(plan=plan, nodes=nodes)


class TestDriveSubgraphSeam:
    """Direct tests for ``GenericPlanInterpreter._drive_subgraph``."""

    @pytest.mark.asyncio
    async def test_returns_outer_state_when_no_subgraph_ref(self) -> None:
        # Edge with subgraph_ref=None should be a no-op pass-through.
        edge = PhaseEdge(source="reflect.main", target="remember.main", when="true")
        interpreter = GenericPlanInterpreter()
        before = _state()
        after = await interpreter._drive_subgraph(
            outer_edge=edge,
            outer_state=before,
            current_node_id="reflect.main",
            depth=1,
        )
        assert after is before

    @pytest.mark.asyncio
    async def test_happy_path_resolves_and_invokes_subgraph(self) -> None:
        """The recursion enters and the subgraph's identity is preserved.

        We don't drive a real executor (the test fixture is minimal);
        we only verify that ``_drive_subgraph`` reached the subgraph
        builder and propagated ``outer_state`` through the recursion
        seam. The full end-to-end execution is exercised by the
        declarative integration suite.
        """
        sub = _sub_plan()
        calls: list[str] = []

        def factory(plan: CompiledRunPlan) -> ExecutablePlan:
            calls.append(plan.profile_path)
            raise _StopRecursionError  # unwind without invoking executor

        interpreter = GenericPlanInterpreter(
            subgraph_resolver=_StubResolver({"bundles/reflect-subgraph.yaml": sub}),
            subgraph_executable_factory=factory,
        )
        with pytest.raises(_StopRecursionError):
            await interpreter._drive_subgraph(
                outer_edge=_outer_edge_with_ref(),
                outer_state=_state(),
                current_node_id="reflect.main",
                depth=1,
            )
        assert calls == ["sub://reflect-subgraph-test"]

    @pytest.mark.asyncio
    async def test_depth_limit_raises_pg_005(self) -> None:
        interpreter = GenericPlanInterpreter(
            subgraph_resolver=_StubResolver(),
            subgraph_executable_factory=_executable_for,
        )
        with pytest.raises(DeclarativeValidationError) as excinfo:
            await interpreter._drive_subgraph(
                outer_edge=_outer_edge_with_ref(),
                outer_state=_state(),
                current_node_id="reflect.main",
                depth=MAX_SUBGRAPH_DEPTH + 1,
            )
        assert excinfo.value.code == "PG-005"

    @pytest.mark.asyncio
    async def test_missing_resolver_raises_pg_005(self) -> None:
        # No resolver wired → subgraph execution is impossible.
        interpreter = GenericPlanInterpreter(subgraph_executable_factory=_executable_for)
        with pytest.raises(DeclarativeValidationError) as excinfo:
            await interpreter._drive_subgraph(
                outer_edge=_outer_edge_with_ref(),
                outer_state=_state(),
                current_node_id="reflect.main",
                depth=1,
            )
        assert excinfo.value.code == "PG-005"
        assert "subgraph_resolver" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_missing_factory_raises_pg_005(self) -> None:
        sub = _sub_plan()
        interpreter = GenericPlanInterpreter(
            subgraph_resolver=_StubResolver({"bundles/reflect-subgraph.yaml": sub}),
        )
        with pytest.raises(DeclarativeValidationError) as excinfo:
            await interpreter._drive_subgraph(
                outer_edge=_outer_edge_with_ref(),
                outer_state=_state(),
                current_node_id="reflect.main",
                depth=1,
            )
        assert excinfo.value.code == "PG-005"
        assert "subgraph_executable_factory" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_resolver_returning_non_plan_raises_pg_005(self) -> None:
        interpreter = GenericPlanInterpreter(
            subgraph_resolver=_StubResolver({"bundles/reflect-subgraph.yaml": "not a plan"}),
            subgraph_executable_factory=_executable_for,
        )
        with pytest.raises(DeclarativeValidationError) as excinfo:
            await interpreter._drive_subgraph(
                outer_edge=_outer_edge_with_ref(),
                outer_state=_state(),
                current_node_id="reflect.main",
                depth=1,
            )
        assert excinfo.value.code == "PG-005"


class _StubResolver:
    def __init__(self, mapping: dict[str, object] | None = None) -> None:
        self._mapping = dict(mapping or {})

    def resolve(self, plan_ref: str) -> object | None:
        return self._mapping.get(plan_ref)


class _StopRecursionError(Exception):
    """Sentinel that the factory raises to short-circuit further recursion."""
