"""ADR-0075 Task 2: phase-run cursor for checkpoint and resume.

Tests that GenericPlanInterpreter exposes a PhaseRunCursor on every result,
and that resume() can continue from a saved cursor without re-executing
completed effects.
"""

from __future__ import annotations

import pytest

from lca.contracts.protocols.declarative_phase_graph import (
    PhaseRunCursor,
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


@pytest.mark.asyncio
async def test_interpretation_result_has_cursor_after_run(standard_plan) -> None:
    """After a successful run, InterpretationResult must expose a PhaseRunCursor."""
    capabilities = {
        f"phase.{phase.value}.standard": StandardPhaseExecutor(phase)
        for phase in SemanticPhase
    }
    executable = GraphAssembler().assemble(standard_plan, MappingRestrictedScope(capabilities))
    result = await GenericPlanInterpreter().run(executable, state={"immutable": True})
    
    assert result.cursor is not None
    assert isinstance(result.cursor, PhaseRunCursor)
    assert result.cursor.plan_ref == compiled_run_plan_ref(standard_plan)
    assert result.cursor.node_id == "stop.main"  # terminal node


@pytest.mark.asyncio
async def test_cursor_contains_all_state(standard_plan) -> None:
    """PhaseRunCursor must be a frozen dataclass with all required fields."""
    capabilities = {
        f"phase.{phase.value}.standard": StandardPhaseExecutor(phase)
        for phase in SemanticPhase
    }
    executable = GraphAssembler().assemble(standard_plan, MappingRestrictedScope(capabilities))
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
    capabilities = {
        f"phase.{phase.value}.standard": StandardPhaseExecutor(phase)
        for phase in SemanticPhase
    }
    executable = GraphAssembler().assemble(standard_plan, MappingRestrictedScope(capabilities))
    interpreter = GenericPlanInterpreter()
    
    # First run: execute the full graph
    first = await interpreter.run(executable, state={"immutable": True})
    cursor = first.cursor
    assert cursor is not None
    assert cursor.node_id == "stop.main"  # completed all nodes
    
    # Resume from the terminal cursor: should complete immediately
    resumed = await interpreter.resume(executable, state=first.state, cursor=cursor)
    
    # Should terminate at the same node
    assert resumed.terminal_node == "stop.main"


@pytest.mark.asyncio
async def test_resume_rejects_cursor_from_different_plan(standard_plan) -> None:
    """Resume must reject a cursor whose plan_ref doesn't match the executable plan."""
    from lca.contracts.protocols.declarative_phase_graph import DeclarativeValidationError
    
    capabilities = {
        f"phase.{phase.value}.standard": StandardPhaseExecutor(phase)
        for phase in SemanticPhase
    }
    executable = GraphAssembler().assemble(standard_plan, MappingRestrictedScope(capabilities))
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
