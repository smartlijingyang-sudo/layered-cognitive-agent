"""R8 tests for ``DefaultReducer.apply_terminal_outcome`` split helpers.

The 140-line ``apply_terminal_outcome`` was split into three private helpers:

- ``_classify_kind`` — the state.status → TerminalOutcomeKind ladder.
- ``_build_error_ref`` — the ErrorRef ladder required by ADR-0077.
- ``_zero_output_fallback_message`` — single source for the Chinese
  zero-output fallback string.

These tests drive the real shipped ``DefaultReducer`` (not a re-implementation)
to lock the contract each helper exposes and to assert that the orchestrator
+helpers still produce the same ``TerminalOutcome`` as the pre-split method.
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.enums import ActionType
from lca.contracts.models.core.decision import Decision, Observation, Turn
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.core.stop import StopDecision, StopReason
from lca.contracts.models.core.terminal_outcome import (
    ErrorRef,
    ResumeCursor,
    TerminalOutcome,
    TerminalOutcomeKind,
    TextRef,
)
from lca.contracts.protocols.declarative.declarative_common import DeclarativeValidationError
from lca.plugins.runtime.reducer import DefaultReducer


def _state(status: TaskStatus = TaskStatus.WORKING) -> AgentState:
    return AgentState(trace_id="trace-1", task="t", budget=Budget(), status=status)


def _decision(
    *,
    action_type: str = ActionType.RESPOND,
    response_text: str | None = None,
) -> Decision:
    return Decision(
        decision_id="dec-1",
        action_type=action_type,
        rationale="test",
        confidence=0.5,
        response_text=response_text,
    )


def _turn(
    *,
    action_type: str = ActionType.RESPOND,
    response_text: str | None = None,
) -> Turn:
    return Turn(
        decision=_decision(action_type=action_type, response_text=response_text),
        observation=Observation(observation_id="obs", success=True, payload=None),
    )


def _reducer() -> DefaultReducer:
    return DefaultReducer()


# ---------------------------------------------------------------------------
# _zero_output_fallback_message — single-source Chinese fallback
# ---------------------------------------------------------------------------


class TestZeroOutputFallbackMessage:
    """The helper is the single source of truth for the zero-output message."""

    def test_returns_non_empty_string(self) -> None:
        msg = DefaultReducer._zero_output_fallback_message()
        assert isinstance(msg, str)
        assert msg  # non-empty

    def test_mentions_zero_output(self) -> None:
        msg = DefaultReducer._zero_output_fallback_message()
        assert "未产生任何输出" in msg

    def test_returns_consistent_value_across_calls(self) -> None:
        """Both call sites (WORKING ladder, COMPLETED zero-output ladder) must
        read the same string — equality, not just substring containment.
        """
        a = DefaultReducer._zero_output_fallback_message()
        b = DefaultReducer._zero_output_fallback_message()
        assert a == b


# ---------------------------------------------------------------------------
# _classify_kind — the status → kind ladder
# ---------------------------------------------------------------------------


class TestClassifyKind:
    """Drive ``_classify_kind`` directly through every status branch."""

    def test_working_without_output_becomes_failed_with_fallback_message(self) -> None:
        state = _state(TaskStatus.WORKING)
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.BUDGET_EXCEEDED,
            final_output=None,
            status=TaskStatus.WORKING,
        )
        kind, materialized_text = _reducer()._classify_kind(state, stop, response_text=None)

        assert kind is TerminalOutcomeKind.FAILED
        assert state.status is TaskStatus.FAILED
        assert state.last_error == DefaultReducer._zero_output_fallback_message()
        assert materialized_text is None

    def test_working_with_output_promotes_to_completed(self) -> None:
        """WORKING + should_stop + non-empty response_text is authoritative."""
        state = _state(TaskStatus.WORKING)
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.TASK_COMPLETED,
            final_output="hello",
            status=None,  # legacy producer omits status
        )
        kind, materialized_text = _reducer()._classify_kind(state, stop, response_text="hello")

        assert kind is TerminalOutcomeKind.COMPLETED
        assert state.status is TaskStatus.COMPLETED
        assert materialized_text == "hello"
        # _classify_kind must not clobber a pre-existing last_error on this path
        assert not state.last_error

    def test_completed_with_output_stays_completed(self) -> None:
        state = _state(TaskStatus.COMPLETED)
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.TASK_COMPLETED,
            final_output="done",
            status=TaskStatus.COMPLETED,
        )
        kind, materialized_text = _reducer()._classify_kind(state, stop, response_text="done")

        assert kind is TerminalOutcomeKind.COMPLETED
        assert state.status is TaskStatus.COMPLETED
        assert materialized_text == "done"

    def test_completed_handoff_with_no_response_text_materializes_marker(self) -> None:
        """HANDOFF carrier with empty response_text becomes a stable marker."""
        state = _state(TaskStatus.COMPLETED)
        state.history.append(_turn(action_type=ActionType.HANDOFF, response_text=None))
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.TASK_COMPLETED,
            final_output=None,
            status=TaskStatus.COMPLETED,
        )
        kind, materialized_text = _reducer()._classify_kind(state, stop, response_text=None)

        assert kind is TerminalOutcomeKind.COMPLETED
        assert materialized_text == "handoff completed"

    def test_completed_without_output_and_not_handoff_becomes_failed(self) -> None:
        """COMPLETED with no output and no HANDOFF → zero-output guard → FAILED."""
        state = _state(TaskStatus.COMPLETED)
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.TASK_COMPLETED,
            final_output=None,
            status=TaskStatus.COMPLETED,
        )
        kind, materialized_text = _reducer()._classify_kind(state, stop, response_text=None)

        assert kind is TerminalOutcomeKind.FAILED
        assert state.status is TaskStatus.FAILED
        assert state.last_error == DefaultReducer._zero_output_fallback_message()
        assert materialized_text is None

    def test_failed_with_existing_error_preserves_error_message(self) -> None:
        state = _state(TaskStatus.FAILED)
        state.last_error = "boom"
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.ERROR,
            final_output=None,
            status=TaskStatus.FAILED,
        )
        kind, materialized_text = _reducer()._classify_kind(state, stop, response_text=None)

        assert kind is TerminalOutcomeKind.FAILED
        assert state.status is TaskStatus.FAILED
        assert state.last_error == "boom"  # not overwritten
        assert materialized_text is None

    def test_failed_without_error_gets_phase_failure_fallback(self) -> None:
        state = _state(TaskStatus.FAILED)
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.ERROR,
            final_output=None,
            status=TaskStatus.FAILED,
        )
        kind, materialized_text = _reducer()._classify_kind(state, stop, response_text=None)

        assert kind is TerminalOutcomeKind.FAILED
        assert "阶段执行失败" in (state.last_error or "")
        assert materialized_text is None

    def test_input_required_becomes_waiting_input(self) -> None:
        state = _state(TaskStatus.INPUT_REQUIRED)
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.CONTINUE,
            final_output=None,
            status=TaskStatus.INPUT_REQUIRED,
        )
        kind, materialized_text = _reducer()._classify_kind(state, stop, response_text=None)

        assert kind is TerminalOutcomeKind.WAITING_INPUT
        assert state.status is TaskStatus.INPUT_REQUIRED
        assert materialized_text is None

    def test_canceled_becomes_canceled(self) -> None:
        state = _state(TaskStatus.CANCELED)
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.CONTINUE,
            final_output=None,
            status=TaskStatus.CANCELED,
        )
        kind, materialized_text = _reducer()._classify_kind(state, stop, response_text=None)

        assert kind is TerminalOutcomeKind.CANCELED
        assert state.status is TaskStatus.CANCELED
        assert materialized_text is None


# ---------------------------------------------------------------------------
# _build_error_ref — the ErrorRef ladder
# ---------------------------------------------------------------------------


class TestBuildErrorRef:
    """Drive ``_build_error_ref`` directly through every branch."""

    def test_failed_with_last_error_uses_last_error(self) -> None:
        state = _state()
        state.last_error = "boom"
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.ERROR,
            final_output=None,
            status=TaskStatus.FAILED,
        )
        ref = _reducer()._build_error_ref(state, TerminalOutcomeKind.FAILED, stop)

        assert isinstance(ref, ErrorRef)
        assert ref.kind == "error"
        assert ref.message == "boom"
        assert ref.source_ref == ""

    def test_failed_without_last_error_falls_back_to_stop_reason(self) -> None:
        state = _state()
        assert not state.last_error
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.ERROR,
            final_output=None,
            status=TaskStatus.FAILED,
        )
        ref = _reducer()._build_error_ref(state, TerminalOutcomeKind.FAILED, stop)

        assert isinstance(ref, ErrorRef)
        assert ref.kind == "error"
        assert ref.message == StopReason.ERROR.value
        assert ref.source_ref == ""

    def test_canceled_without_last_error_uses_canceled_default(self) -> None:
        state = _state()
        assert not state.last_error
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.CONTINUE,
            final_output=None,
            status=TaskStatus.CANCELED,
        )
        ref = _reducer()._build_error_ref(state, TerminalOutcomeKind.CANCELED, stop)

        assert isinstance(ref, ErrorRef)
        assert ref.kind == "canceled"
        assert ref.message == "canceled"

    def test_degraded_without_last_error_uses_degraded_default(self) -> None:
        state = _state()
        assert not state.last_error
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.CONTINUE,
            final_output=None,
            status=None,
        )
        ref = _reducer()._build_error_ref(state, TerminalOutcomeKind.DEGRADED, stop)

        assert isinstance(ref, ErrorRef)
        assert ref.kind == "degraded"
        assert ref.message == "degraded"

    def test_completed_returns_none(self) -> None:
        state = _state()
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.TASK_COMPLETED,
            final_output="ok",
            status=TaskStatus.COMPLETED,
        )
        ref = _reducer()._build_error_ref(state, TerminalOutcomeKind.COMPLETED, stop)

        assert ref is None

    def test_waiting_input_returns_none(self) -> None:
        state = _state()
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.CONTINUE,
            final_output=None,
            status=TaskStatus.INPUT_REQUIRED,
        )
        ref = _reducer()._build_error_ref(state, TerminalOutcomeKind.WAITING_INPUT, stop)

        assert ref is None


# ---------------------------------------------------------------------------
# apply_terminal_outcome — orchestrator + helpers end-to-end regression
# ---------------------------------------------------------------------------


class TestOrchestratorEndToEnd:
    """Regression: orchestrator + helpers produce the same outcomes as before."""

    def test_completed_with_output(self) -> None:
        state = _state(TaskStatus.WORKING)
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.TASK_COMPLETED,
            final_output="Hello, world!",
            status=TaskStatus.COMPLETED,
        )
        outcome = _reducer().apply_terminal_outcome(
            state, stop, plan_ref="test-plan", journal_seq_end=42
        )

        assert isinstance(outcome, TerminalOutcome)
        assert outcome.kind is TerminalOutcomeKind.COMPLETED
        assert isinstance(outcome.final_output_ref, TextRef)
        assert outcome.final_output_ref.text == "Hello, world!"
        assert outcome.final_output_ref.seq == 42
        assert outcome.plan_ref == "test-plan"
        assert outcome.journal_seq_end == 42
        assert outcome.error_ref is None
        assert outcome.resume_cursor is None

    def test_output_without_optional_status_is_completed(self) -> None:
        """Legacy producer omits status; non-empty output is authoritative."""
        state = _state(TaskStatus.WORKING)
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.TASK_COMPLETED,
            final_output="legacy output",
            status=None,
        )
        outcome = _reducer().apply_terminal_outcome(
            state, stop, plan_ref="test-plan", journal_seq_end=11
        )

        assert outcome.kind is TerminalOutcomeKind.COMPLETED
        assert outcome.final_output_ref is not None
        assert outcome.final_output_ref.text == "legacy output"
        assert outcome.stop_reason == StopReason.TASK_COMPLETED.value

    def test_failed_without_output(self) -> None:
        state = _state(TaskStatus.WORKING)
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.BUDGET_EXCEEDED,
            final_output=None,
            status=TaskStatus.WORKING,
        )
        outcome = _reducer().apply_terminal_outcome(
            state, stop, plan_ref="test-plan", journal_seq_end=10
        )

        assert outcome.kind is TerminalOutcomeKind.FAILED
        assert outcome.error_ref is not None
        assert outcome.error_ref.message == DefaultReducer._zero_output_fallback_message()
        assert outcome.final_output_ref is None

    def test_failed_with_existing_error_uses_error_message(self) -> None:
        state = _state(TaskStatus.FAILED)
        state.last_error = "Something went wrong"
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.ERROR,
            final_output=None,
            status=TaskStatus.FAILED,
        )
        outcome = _reducer().apply_terminal_outcome(
            state, stop, plan_ref="test-plan", journal_seq_end=5
        )

        assert outcome.kind is TerminalOutcomeKind.FAILED
        assert outcome.error_ref is not None
        assert outcome.error_ref.message == "Something went wrong"

    def test_waiting_input_without_cursor_raises(self) -> None:
        state = _state(TaskStatus.INPUT_REQUIRED)
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.CONTINUE,
            final_output=None,
            status=TaskStatus.INPUT_REQUIRED,
        )
        with pytest.raises(DeclarativeValidationError, match="durable resume cursor"):
            _reducer().apply_terminal_outcome(state, stop, plan_ref="test-plan", journal_seq_end=15)

    def test_waiting_input_with_cursor_succeeds(self) -> None:
        state = _state(TaskStatus.INPUT_REQUIRED)
        cursor = ResumeCursor(cursor="cur-1", session_seq=2, approval_id="app-1")
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.CONTINUE,
            final_output=None,
            status=TaskStatus.INPUT_REQUIRED,
        )
        outcome = _reducer().apply_terminal_outcome(
            state, stop, plan_ref="test-plan", journal_seq_end=15, resume_cursor=cursor
        )

        assert outcome.kind is TerminalOutcomeKind.WAITING_INPUT
        assert outcome.resume_cursor is cursor

    def test_canceled_kind_and_error_ref(self) -> None:
        state = _state(TaskStatus.CANCELED)
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.CONTINUE,
            final_output=None,
            status=TaskStatus.CANCELED,
        )
        outcome = _reducer().apply_terminal_outcome(
            state, stop, plan_ref="test-plan", journal_seq_end=20
        )

        assert outcome.kind is TerminalOutcomeKind.CANCELED
        assert outcome.final_output_ref is None
        # ADR-0077 invariant: CANCELED requires error_ref or final_output_ref
        assert outcome.error_ref is not None
        assert outcome.error_ref.kind == "canceled"

    def test_working_terminal_becomes_failed_with_chinese_fallback(self) -> None:
        state = _state(TaskStatus.WORKING)
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.BUDGET_EXCEEDED,
            final_output=None,
            status=None,
        )
        outcome = _reducer().apply_terminal_outcome(
            state, stop, plan_ref="test-plan", journal_seq_end=25
        )

        assert outcome.kind is TerminalOutcomeKind.FAILED
        assert outcome.error_ref is not None
        assert outcome.error_ref.message == DefaultReducer._zero_output_fallback_message()

    def test_handoff_completion_materializes_marker(self) -> None:
        """HANDOFF carrier with no response_text → COMPLETED + 'handoff completed'."""
        state = _state(TaskStatus.COMPLETED)
        state.history.append(_turn(action_type=ActionType.HANDOFF, response_text=None))
        stop = StopDecision(
            should_stop=True,
            reason=StopReason.TASK_COMPLETED,
            final_output=None,
            status=TaskStatus.COMPLETED,
        )
        outcome = _reducer().apply_terminal_outcome(
            state, stop, plan_ref="test-plan", journal_seq_end=33
        )

        assert outcome.kind is TerminalOutcomeKind.COMPLETED
        assert outcome.final_output_ref is not None
        assert outcome.final_output_ref.text == "handoff completed"

    def test_orchestrator_signature_is_unchanged(self) -> None:
        """Public Protocol surface: kwargs are plan_ref, journal_seq_end, resume_cursor."""
        import inspect

        sig = inspect.signature(DefaultReducer.apply_terminal_outcome)
        params = list(sig.parameters)
        assert params[:3] == ["self", "state", "stop"]
        assert "plan_ref" in sig.parameters
        assert "journal_seq_end" in sig.parameters
        assert "resume_cursor" in sig.parameters
        # plan_ref and journal_seq_end are keyword-only
        assert sig.parameters["plan_ref"].kind is inspect.Parameter.KEYWORD_ONLY
        assert sig.parameters["journal_seq_end"].kind is inspect.Parameter.KEYWORD_ONLY
        assert sig.parameters["resume_cursor"].kind is inspect.Parameter.KEYWORD_ONLY
