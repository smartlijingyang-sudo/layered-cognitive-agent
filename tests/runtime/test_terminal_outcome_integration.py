"""Tests for ADR-0077 TerminalOutcome integration.

Verifies that the Reducer produces the sole TerminalOutcome and that
Result fields are derived from it (ADR-0077 §决策三).
"""

from __future__ import annotations

import pytest

from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.core.stop import StopDecision, StopReason
from lca.contracts.models.core.terminal_outcome import (
    TerminalOutcome,
    TerminalOutcomeKind,
    TextRef,
)
from lca.contracts.protocols.declarative.declarative_common import DeclarativeValidationError
from lca.plugins.phase_graph.stop_policy import DefaultStopPolicy
from lca.runtime.reducer import DefaultReducer


class _FixedArtifactClosure:
    def synthesize(self, *, fallback: str = "") -> str | None:
        return "[artifact closure]"


class TestDefaultStopPolicy:
    def test_budget_exceeded_uses_injected_artifact_closure(self) -> None:
        policy = DefaultStopPolicy(_FixedArtifactClosure())
        state = AgentState(
            trace_id="test-trace",
            task="test task",
            budget=Budget(max_steps=0, used_steps=1),
        )
        observation = Observation(observation_id="obs", success=False, payload=None)

        stop = policy.decide(state, None, observation, None)

        assert stop.should_stop is True
        assert stop.final_output == "[artifact closure]"
        assert stop.status == TaskStatus.COMPLETED


class TestReducerApplyTerminalOutcome:
    """Test Reducer.apply_terminal_outcome (ADR-0077 §决策一)."""

    def test_completed_with_output(self) -> None:
        """COMPLETED outcome when stop has final_output."""
        reducer = DefaultReducer()
        state = AgentState(trace_id="test-trace", task="test task", budget=Budget())
        state.status = TaskStatus.WORKING
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.TASK_COMPLETED,
            final_output="Hello, world!",
            status=TaskStatus.COMPLETED,
        )

        outcome = reducer.apply_terminal_outcome(
            state, stop, plan_ref="test-plan", journal_seq_end=42
        )

        assert isinstance(outcome, TerminalOutcome)
        assert outcome.kind == TerminalOutcomeKind.COMPLETED
        assert isinstance(outcome.final_output_ref, TextRef)
        assert outcome.final_output_ref.text == "Hello, world!"
        assert outcome.final_output_ref.seq == 42
        assert outcome.plan_ref == "test-plan"
        assert outcome.journal_seq_end == 42
        assert outcome.error_ref is None
        assert outcome.resume_cursor is None

    def test_output_without_optional_status_is_completed(self) -> None:
        """A terminal output must not be lost when legacy producers omit status."""
        reducer = DefaultReducer()
        state = AgentState(trace_id="test-trace", task="test task", budget=Budget())
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.TASK_COMPLETED,
            final_output="legacy output",
            status=None,
        )

        outcome = reducer.apply_terminal_outcome(
            state, stop, plan_ref="test-plan", journal_seq_end=11
        )

        assert outcome.kind == TerminalOutcomeKind.COMPLETED
        assert isinstance(outcome.final_output_ref, TextRef)
        assert outcome.final_output_ref.text == "legacy output"
        assert outcome.stop_reason == StopReason.TASK_COMPLETED.value

    def test_failed_without_output(self) -> None:
        """FAILED outcome when stop has no output (zero-output guard)."""
        reducer = DefaultReducer()
        state = AgentState(trace_id="test-trace", task="test task", budget=Budget())
        state.status = TaskStatus.WORKING
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.BUDGET_EXCEEDED,
            final_output=None,
            status=TaskStatus.WORKING,
        )

        outcome = reducer.apply_terminal_outcome(
            state, stop, plan_ref="test-plan", journal_seq_end=10
        )

        assert outcome.kind == TerminalOutcomeKind.FAILED
        assert outcome.error_ref is not None
        assert "未产生任何输出" in outcome.error_ref.message
        assert outcome.final_output_ref is None
        assert outcome.plan_ref == "test-plan"
        assert outcome.journal_seq_end == 10

    def test_failed_with_error(self) -> None:
        """FAILED outcome when stop has FAILED status."""
        reducer = DefaultReducer()
        state = AgentState(trace_id="test-trace", task="test task", budget=Budget())
        state.status = TaskStatus.WORKING
        state.last_error = "Something went wrong"
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.ERROR,
            final_output=None,
            status=TaskStatus.FAILED,
        )

        outcome = reducer.apply_terminal_outcome(
            state, stop, plan_ref="test-plan", journal_seq_end=5
        )

        assert outcome.kind == TerminalOutcomeKind.FAILED
        assert outcome.error_ref is not None
        assert outcome.error_ref.message == "Something went wrong"
        assert outcome.final_output_ref is None

    def test_waiting_input(self) -> None:
        """WAITING_INPUT outcome when state has INPUT_REQUIRED status."""
        reducer = DefaultReducer()
        state = AgentState(trace_id="test-trace", task="test task", budget=Budget())
        state.status = TaskStatus.INPUT_REQUIRED
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.ERROR,
            final_output=None,
            status=TaskStatus.INPUT_REQUIRED,
        )

        with pytest.raises(DeclarativeValidationError, match="durable resume cursor"):
            reducer.apply_terminal_outcome(state, stop, plan_ref="test-plan", journal_seq_end=15)

    def test_canceled(self) -> None:
        """CANCELED outcome when state has CANCELED status."""
        reducer = DefaultReducer()
        state = AgentState(trace_id="test-trace", task="test task", budget=Budget())
        state.status = TaskStatus.CANCELED
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.ERROR,
            final_output=None,
            status=TaskStatus.CANCELED,
        )

        outcome = reducer.apply_terminal_outcome(
            state, stop, plan_ref="test-plan", journal_seq_end=20
        )

        assert outcome.kind == TerminalOutcomeKind.CANCELED
        assert outcome.final_output_ref is None
        # ADR-0077: CANCELED requires error_ref or final_output_ref
        assert outcome.error_ref is not None
        assert outcome.error_ref.kind == "canceled"
        assert outcome.resume_cursor is None

    def test_working_at_terminal_is_failed(self) -> None:
        """WORKING status at terminal maps to FAILED (zero-output guard)."""
        reducer = DefaultReducer()
        state = AgentState(trace_id="test-trace", task="test task", budget=Budget())
        state.status = TaskStatus.WORKING
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.ERROR,
            final_output=None,
            status=None,
        )

        outcome = reducer.apply_terminal_outcome(
            state, stop, plan_ref="test-plan", journal_seq_end=25
        )

        # WORKING at terminal means budget exhausted without output = FAILED
        assert outcome.kind == TerminalOutcomeKind.FAILED
        assert outcome.error_ref is not None
        assert "未产生任何输出" in outcome.error_ref.message

    def test_plan_ref_required(self) -> None:
        """TerminalOutcome requires non-empty plan_ref."""
        reducer = DefaultReducer()
        state = AgentState(trace_id="test-trace", task="test task", budget=Budget())
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.TASK_COMPLETED,
            final_output="output",
            status=TaskStatus.COMPLETED,
        )

        with pytest.raises(ValueError, match="plan_ref must be non-empty"):
            reducer.apply_terminal_outcome(state, stop, plan_ref="", journal_seq_end=0)

    def test_journal_seq_end_non_negative(self) -> None:
        """TerminalOutcome requires non-negative journal_seq_end."""
        reducer = DefaultReducer()
        state = AgentState(trace_id="test-trace", task="test task", budget=Budget())
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.TASK_COMPLETED,
            final_output="output",
            status=TaskStatus.COMPLETED,
        )

        with pytest.raises(ValueError, match="journal_seq_end must be non-negative"):
            reducer.apply_terminal_outcome(state, stop, plan_ref="test-plan", journal_seq_end=-1)
