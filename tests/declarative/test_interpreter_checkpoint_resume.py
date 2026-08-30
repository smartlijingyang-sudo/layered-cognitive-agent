"""ADR-0075 Task 2: phase-run cursor for checkpoint and resume.

Tests that GenericPlanInterpreter exposes a PhaseRunCursor on every result,
and that resume() can continue from a saved cursor without re-executing
completed effects.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from lca.contracts.models.core.result import ApprovalPendingError
from lca.contracts.protocols.control_verdict import ControlVerdict, ControlVerdictKind
from lca.contracts.protocols.declarative_phase_graph import (
    PhaseEdge,
    PhaseInput,
    PhaseNode,
    PhaseResult,
    PhaseRunCursor,
    SemanticPhase,
)
from lca.harness.declarative import GenericPlanInterpreter, GraphAssembler, MappingRestrictedScope
from lca.harness.plan import compiled_run_plan_ref
from lca.harness.profile.plan_compiler import compile_plan
from lca.harness.profile.resolve import resolve_profile
from tests.phase_executors import standard_phase_executors


class _ApprovalPendingExecutor:
    """Pause the graph as soon as its act node is visited."""

    async def execute(self, _context: object, _input: PhaseInput) -> PhaseResult:
        raise ApprovalPendingError({"approval_id": "approval-fixture"})


class _AllowContribution:
    """Test stub that always returns an allow verdict for any contribution slot."""

    async def execute(self, _context: object, _input: PhaseInput) -> PhaseResult:
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                plugin_id="test.allow-contribution",
                kind=ControlVerdictKind.ALLOW,
            ),
        )


def _capabilities_for(plan) -> dict[str, object]:
    """All 6 phase executors plus a stub allow contribution per plan binding."""
    capabilities: dict[str, object] = dict(standard_phase_executors())
    allow = _AllowContribution()
    for binding in plan.phase_bindings:
        for contribution in binding.contributions:
            capabilities[contribution.executor] = allow
    return capabilities


@pytest.fixture(scope="module")
def standard_plan():
    return compile_plan(resolve_profile("profiles/web-standard.yaml"))


@pytest.mark.asyncio
async def test_approval_pause_uses_plan_declared_resume_node(standard_plan) -> None:
    """A custom topology owns the durable restart point after human approval."""
    assert standard_plan.phase_graph is not None
    think_binding = next(
        binding
        for binding in standard_plan.phase_bindings
        if binding.semantic_phase is SemanticPhase.THINK
    )
    approval_think_id = "think.after-approval"
    plan = replace(
        standard_plan,
        phase_graph=replace(
            standard_plan.phase_graph,
            nodes=(
                *standard_plan.phase_graph.nodes,
                PhaseNode(
                    id=approval_think_id,
                    semantic_phase=SemanticPhase.THINK,
                    binding=think_binding.executor_capability,
                    max_visits=8,
                ),
            ),
            edges=(
                *standard_plan.phase_graph.edges,
                PhaseEdge(
                    source=approval_think_id,
                    target="act.main",
                    when="true",
                ),
            ),
            approval_resume_node=approval_think_id,
        ),
        phase_bindings=(
            *standard_plan.phase_bindings,
            replace(think_binding, node_id=approval_think_id),
        ),
    )
    capabilities = _capabilities_for(plan)
    capabilities["phase.act.standard"] = _ApprovalPendingExecutor()
    executable = GraphAssembler().assemble(plan, MappingRestrictedScope(capabilities))

    result = await GenericPlanInterpreter().run(executable, state={"immutable": True})

    assert result.outcome is not None
    assert result.outcome.kind == "paused"
    assert result.cursor is not None
    assert result.cursor.node_id == approval_think_id


@pytest.mark.asyncio
async def test_approval_pause_without_declared_resume_node_fails_closed(standard_plan) -> None:
    """Approval cannot create a durable cursor from an interpreter-owned default."""
    assert standard_plan.phase_graph is not None
    plan = replace(
        standard_plan,
        phase_graph=replace(standard_plan.phase_graph, approval_resume_node=None),
    )
    capabilities = _capabilities_for(plan)
    capabilities["phase.act.standard"] = _ApprovalPendingExecutor()
    executable = GraphAssembler().assemble(plan, MappingRestrictedScope(capabilities))

    result = await GenericPlanInterpreter().run(executable, state={"immutable": True})

    assert result.outcome is not None
    assert result.outcome.kind == "failed"
    assert result.outcome.error_fact is not None
    assert result.outcome.error_fact.payload["error_code"] == "PG-008"


@pytest.mark.asyncio
async def test_interpretation_result_has_cursor_after_run(standard_plan) -> None:
    """After a successful run, InterpretationResult must expose a PhaseRunCursor."""
    executable = GraphAssembler().assemble(
        standard_plan, MappingRestrictedScope(_capabilities_for(standard_plan))
    )
    result = await GenericPlanInterpreter().run(executable, state={"immutable": True})

    assert result.cursor is not None
    assert isinstance(result.cursor, PhaseRunCursor)
    assert result.cursor.plan_ref == compiled_run_plan_ref(standard_plan)
    assert result.cursor.node_id == "stop.main"  # terminal node


@pytest.mark.asyncio
async def test_cursor_contains_all_state(standard_plan) -> None:
    """PhaseRunCursor must be a frozen dataclass with all required fields."""
    executable = GraphAssembler().assemble(
        standard_plan, MappingRestrictedScope(_capabilities_for(standard_plan))
    )
    result = await GenericPlanInterpreter().run(executable, state={"immutable": True})
    cursor = result.cursor

    assert cursor is not None
    assert cursor.plan_ref
    assert cursor.node_id
    assert isinstance(cursor.visit_counts, tuple)
    assert isinstance(cursor.edge_counts, tuple)
    assert isinstance(cursor.artifacts, dict)
    assert isinstance(cursor.causation_refs, tuple)
    assert isinstance(cursor.budget_snapshot, dict)


@pytest.mark.asyncio
async def test_resume_from_terminal_cursor_is_noop(standard_plan) -> None:
    """Resume from a terminal cursor should complete immediately without re-execution."""
    executable = GraphAssembler().assemble(
        standard_plan, MappingRestrictedScope(_capabilities_for(standard_plan))
    )
    interpreter = GenericPlanInterpreter()

    # First run: execute the full graph
    first = await interpreter.run(executable, state={"immutable": True})
    cursor = first.cursor
    assert cursor is not None
    assert cursor.node_id == "stop.main"  # completed all nodes

    resumed = await interpreter.resume(executable, state=first.state, cursor=cursor)

    assert resumed.terminal_node == "stop.main"
    assert resumed.outcome is not None
    assert resumed.outcome.kind == "completed"


@pytest.mark.asyncio
async def test_resume_rejects_cursor_from_different_plan(standard_plan) -> None:
    """Resume must reject a cursor whose plan_ref doesn't match the executable plan."""
    from lca.contracts.protocols.declarative_phase_graph import DeclarativeValidationError

    executable = GraphAssembler().assemble(
        standard_plan, MappingRestrictedScope(_capabilities_for(standard_plan))
    )
    interpreter = GenericPlanInterpreter()

    result = await interpreter.run(executable, state={"immutable": True})
    cursor = result.cursor
    assert cursor is not None

    # Tamper with the plan_ref
    tampered_cursor = PhaseRunCursor(
        plan_ref="different-plan-hash",
        node_id=cursor.node_id,
        visit_counts=cursor.visit_counts,
        edge_counts=cursor.edge_counts,
        artifacts=cursor.artifacts,
        causation_refs=cursor.causation_refs,
        budget_snapshot=cursor.budget_snapshot,
    )

    with pytest.raises(DeclarativeValidationError, match="plan_ref"):
        await interpreter.resume(executable, state=result.state, cursor=tampered_cursor)
