"""ADR-0075 Task 3: Declarative run outcomes for pause, failure, and effect uncertainty.

Tests that GenericPlanInterpreter and DeclarativeRuntimeDriver converge all
execution outcomes (completed, paused, failed, effect_uncertain) into a
standard DeclarativeRunOutcome type, rather than raising exceptions or
returning ambiguous Result objects.
"""

from __future__ import annotations

import pytest

from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.stop import StopDecision, StopReason
from lca.contracts.protocols.command_envelope import RunDelta
from lca.contracts.protocols.control_verdict import ControlVerdict, ControlVerdictKind
from lca.contracts.protocols.declarative_phase_graph import (
    DeclarativeRunOutcome,
    PhaseInput,
    PhaseResult,
    PhaseRunCursor,
)
from lca.harness.declarative import GenericPlanInterpreter, GraphAssembler, MappingRestrictedScope
from lca.harness.declarative.phase_governance import classify_control_verdict
from lca.harness.plan import compiled_run_plan_ref
from lca.harness.profile.plan_compiler import compile_plan
from lca.harness.profile.resolve import resolve_profile
from tests.phase_executors import standard_phase_executors


@pytest.fixture(scope="module")
def standard_plan():
    return compile_plan(resolve_profile("profiles/web-standard.yaml"))


class _AllowContribution:
    async def execute(self, _context, _input: PhaseInput) -> PhaseResult:
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                plugin_id="test.allow-contribution",
                kind=ControlVerdictKind.ALLOW,
            ),
        )


class _TerminalStopExecutor:
    async def execute(self, _context, _input: PhaseInput) -> PhaseResult:
        return PhaseResult(
            result_kind="stop_decision",
            payload=StopDecision(
                should_stop=True,
                reason=StopReason.TASK_COMPLETED,
                final_output="preserved output",
                status=TaskStatus.COMPLETED,
            ),
        )


class _LegacyTerminalPayloadExecutor:
    """Represent a legacy stop executor that does not satisfy the typed contract."""

    async def execute(self, _context, _input: PhaseInput) -> PhaseResult:
        return PhaseResult(
            result_kind="stop_decision",
            payload={"should_stop": True},
        )


def _capabilities_for(plan):
    capabilities = dict(standard_phase_executors())
    allow = _AllowContribution()
    for binding in plan.phase_bindings:
        for contribution in binding.contributions:
            capabilities[contribution.executor] = allow
    return capabilities


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (ControlVerdictKind.ALLOW, "allow"),
        (ControlVerdictKind.DENY, "deny"),
        (ControlVerdictKind.EXHAUSTED, "stop"),
        (ControlVerdictKind.STOP, "stop"),
        (ControlVerdictKind.ASK_HUMAN, "pause"),
        (ControlVerdictKind.REWRITE, "rewrite"),
    ],
)
def test_govern_verdict_uses_closed_typed_vocabulary(kind, expected) -> None:
    """Every supported control meaning has one shared contract representation."""
    assert classify_control_verdict(ControlVerdict(plugin_id="test.control", kind=kind)) == expected


def test_govern_verdict_rejects_legacy_dictionary_payload() -> None:
    """A malformed control result must fail closed rather than silently allow."""
    from lca.contracts.protocols.declarative_phase_graph import DeclarativeValidationError

    with pytest.raises(DeclarativeValidationError, match="ControlVerdict") as exc_info:
        classify_control_verdict({"verdict": "allow"})

    assert exc_info.value.code == "RT-004"


def test_interpreter_rejects_state_delta_without_reducer() -> None:
    """A state-changing phase cannot run without the only permitted writer."""
    from lca.contracts.protocols.declarative_phase_graph import DeclarativeValidationError

    with pytest.raises(DeclarativeValidationError, match="no DeltaReducer") as exc_info:
        GenericPlanInterpreter()._apply_delta(
            {"immutable": True},
            RunDelta(plan_ref="test-plan", metadata={"operation": "step"}),
        )

    assert exc_info.value.code == "RT-001"


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
async def test_terminal_outcome_preserves_stop_decision_metadata(standard_plan) -> None:
    """Terminal graph closure must not discard the stop phase's output/status."""
    capabilities = _capabilities_for(standard_plan)
    capabilities["phase.stop.standard"] = _TerminalStopExecutor()
    executable = GraphAssembler().assemble(standard_plan, MappingRestrictedScope(capabilities))

    result = await GenericPlanInterpreter().run(executable, state={"immutable": True})

    assert result.outcome is not None
    assert result.outcome.kind == "completed"
    assert result.outcome.stop.final_output == "preserved output"
    assert result.outcome.stop.status is TaskStatus.COMPLETED
    assert result.outcome.stop.reason is StopReason.TASK_COMPLETED


@pytest.mark.asyncio
async def test_terminal_phase_rejects_legacy_mapping_payload(standard_plan) -> None:
    """A terminal node cannot silently complete without a StopDecision."""
    capabilities = _capabilities_for(standard_plan)
    capabilities["phase.stop.standard"] = _LegacyTerminalPayloadExecutor()
    executable = GraphAssembler().assemble(standard_plan, MappingRestrictedScope(capabilities))

    result = await GenericPlanInterpreter().run(executable, state={"immutable": True})

    assert result.outcome is not None
    assert result.outcome.kind == "failed"
    assert result.outcome.error_fact is not None
    assert result.outcome.error_fact.payload["error_code"] == "RT-002"


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


def test_outcome_projector_records_failure_without_executing_a_graph() -> None:
    """Terminal failure projection has a direct test surface independent of traversal."""

    from lca.harness.declarative import InMemoryJournalCommitter
    from lca.harness.declarative.outcome_projection import RunOutcomeProjector
    from lca.harness.declarative.traversal import PhaseTraversal

    journal = InMemoryJournalCommitter()
    traversal = PhaseTraversal.start(
        plan_ref="test-plan",
        entry_node_id="think.standard",
        artifacts={"task": "test"},
        input=None,
    )

    result = RunOutcomeProjector(journal).failed(
        ValueError("synthetic failure"),
        traversal=traversal,
        state={"immutable": True},
        plan_ref="test-plan",
        visits=[],
        facts=[],
        reason="execution_error",
    )

    assert result.outcome is not None
    assert result.outcome.kind == "failed"
    assert result.outcome.error_fact is not None
    assert result.outcome.error_fact.payload["error"] == "synthetic failure"
    assert journal.facts == [result.outcome.error_fact]
