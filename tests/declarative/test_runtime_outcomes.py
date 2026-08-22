"""ADR-0075 Task 3: Declarative run outcomes for pause, failure, and effect uncertainty.

Tests that GenericPlanInterpreter and DeclarativeRuntimeDriver converge all
execution outcomes (completed, paused, failed, effect_uncertain) into a
standard DeclarativeRunOutcome type, rather than raising exceptions or
returning ambiguous Result objects.
"""

from __future__ import annotations

import pytest

from lca.contracts.protocols.declarative_phase_graph import (
    DeclarativeRunOutcome,
    PhaseInput,
    PhaseResult,
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


class _AllowContribution:
    async def execute(self, _context, _input: PhaseInput) -> PhaseResult:
        return PhaseResult(result_kind="control", payload={"verdict": "allow"})


def _capabilities_for(plan):
    capabilities = {
        f"phase.{phase.value}.standard": StandardPhaseExecutor(phase)
        for phase in SemanticPhase
    }
    allow = _AllowContribution()
    for binding in plan.phase_bindings:
        for contribution in binding.contributions:
            capabilities[contribution.executor] = allow
    return capabilities


@pytest.mark.asyncio
async def test_completed_run_returns_completed_outcome(standard_plan) -> None:
    """A successful run should return an outcome with kind='completed'."""
    capabilities = _capabilities_for(standard_plan)
    executable = GraphAssembler().assemble(standard_plan, MappingRestrictedScope(capabilities))
    interpreter = GenericPlanInterpreter()

    result = await interpreter.run(executable, state={"immutable": True})

    assert result.outcome is not None
    assert isinstance(result.outcome, DeclarativeRunOutcome)
    assert result.outcome.kind == "completed"
    assert result.outcome.cursor is not None
    assert result.outcome.stop is not None
    assert result.outcome.stop.should_stop is True


@pytest.mark.asyncio
async def test_outcome_contains_cursor_and_stop_decision(standard_plan) -> None:
    """Outcome must carry cursor and stop decision for downstream consumers."""
    capabilities = _capabilities_for(standard_plan)
    executable = GraphAssembler().assemble(standard_plan, MappingRestrictedScope(capabilities))
    interpreter = GenericPlanInterpreter()

    result = await interpreter.run(executable, state={"immutable": True})
    outcome = result.outcome

    assert outcome is not None
    assert isinstance(outcome.cursor, PhaseRunCursor)
    assert outcome.cursor.plan_ref == compiled_run_plan_ref(standard_plan)
    assert outcome.stop is not None
    assert outcome.stop.should_stop is True
    assert outcome.error_fact is None  # no error in completed run


@pytest.mark.asyncio
async def test_validation_error_maps_to_failed_outcome(standard_plan) -> None:
    """When the interpreter raises DeclarativeValidationError, it should be
    caught and converted to a failed outcome, not propagated."""
    capabilities = _capabilities_for(standard_plan)
    # Tamper with the plan to cause a validation error.

    broken_plan = standard_plan
    # Create a broken graph with missing node
    from dataclasses import replace

    broken_graph = replace(
        standard_plan.phase_graph,
        entry="nonexistent.node",
    )
    broken_plan = replace(standard_plan, phase_graph=broken_graph)
    broken_executable = GraphAssembler().assemble(broken_plan, MappingRestrictedScope(capabilities))

    interpreter = GenericPlanInterpreter()

    # Should not raise; should return a failed outcome
    result = await interpreter.run(broken_executable, state={"immutable": True})

    assert result.outcome is not None
    assert result.outcome.kind == "failed"
    assert result.outcome.error_fact is not None
    assert result.outcome.cursor is not None  # cursor captured at failure point


@pytest.mark.asyncio
async def test_outcome_kind_is_literal_type() -> None:
    """DeclarativeRunOutcome.kind must be a Literal type."""
    from typing import get_args, get_type_hints

    hints = get_type_hints(DeclarativeRunOutcome)
    kind_type = hints.get("kind")

    # Should be a Literal type
    assert kind_type is not None
    # Check that it's one of the expected kinds
    literal_args = get_args(kind_type)
    assert "completed" in literal_args
    assert "paused" in literal_args
    assert "failed" in literal_args
    assert "effect_uncertain" in literal_args
