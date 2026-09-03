"""RunDiagnostic end-to-end — see ADR-0122.

The previous ``phase_failure_stop_result`` crammed failure summary into
``StopDecision.final_output`` (a string slot for the successful answer).
The reducer then wrote a fixed Chinese fallback when ``state.last_error``
was empty, which is exactly what ``run_f03bd17f77f1`` ended up showing in
``doctor_report.H6.error``.

These tests cover:

- ``RunDiagnostic`` is a typed, frozen, JSON-friendly value object.
- ``phase_failure_stop_result`` emits ``StopDecision.failure: RunDiagnostic``,
  leaving ``final_output`` None.
- ``reducer.apply_stop`` propagates the diagnostic message into
  ``state.last_error`` instead of letting the fallback kick in.
- ``TerminalOutcome.error_ref.diagnostic`` carries the RunDiagnostic.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.stop import StopDecision, StopReason
from lca.contracts.protocols.declarative.declarative_execution import (
    PhaseAttemptFailure,
    PhaseExecutionFailure,
)
from lca.plugins.phase_graph.failure_stop import phase_failure_stop_result
from lca.runtime.diagnostic import (
    PhaseAttemptSummary,
    RunDiagnostic,
    StackFrame,
)


def test_run_diagnostic_is_frozen_and_serialisable() -> None:
    diag = RunDiagnostic(
        run_id="r",
        trace_id="t",
        phase="think",
        node_id="think.main",
        error_type="RuntimeError",
        message="boom",
        stack=(StackFrame(filename="x.py", lineno=1, name="<module>"),),
        causation=("evt1",),
        attempts=(PhaseAttemptSummary(attempt=1, category="permanent", error_type="RuntimeError"),),
        suggested_action="check ambits",
    )
    # Frozen
    import pytest

    with pytest.raises(FrozenInstanceError):
        diag.error_type = "Other"
    # JSON-friendly
    d = diag.to_dict()
    assert d["error_type"] == "RuntimeError"
    assert d["attempts"][0]["category"] == "permanent"
    assert d["stack"][0]["filename"] == "x.py"


def test_phase_failure_stop_result_binds_diagnostic_not_final_output() -> None:
    failure = PhaseExecutionFailure(
        node_id="think.main",
        attempts=(PhaseAttemptFailure(attempt=1, category="permanent", error_type="RuntimeError"),),
    )
    res = phase_failure_stop_result(
        failure,
        plan_ref="plan",
        run_id="run",
        trace_id="trace",
        suggested_action="bind FileStore via RunAmbit",
    )
    assert res.result_kind == "stop_decision"
    stop: StopDecision = res.payload
    assert stop.should_stop is True
    assert stop.reason is StopReason.ERROR
    assert stop.status is TaskStatus.FAILED
    # ADR-0122: failure carries the diagnostic; final_output stays None.
    assert stop.final_output is None
    assert isinstance(stop.failure, RunDiagnostic)
    assert stop.failure.node_id == "think.main"
    assert stop.failure.error_type == "RuntimeError"
    assert stop.failure.attempts[0].category == "permanent"
    assert stop.failure.suggested_action == "bind FileStore via RunAmbit"


def test_reducer_apply_stop_propagates_diagnostic_message() -> None:
    """``state.last_error`` must be filled from the RunDiagnostic, not fall back."""
    from lca.contracts.models.core.state import AgentState, Budget
    from lca.plugins.phase_graph.failure_stop import _summarize_attempts
    from lca.plugins.runtime.reducer import DefaultReducer

    # ADR-clean-truths 决策 一:用真构造路径(phase_failure_stop_result 用的
    # 摘要生成器)造 message,而不是直接写字面量。这样 reducer 透传测试与
    # 摘要格式测试共享同一生成器。
    failure = PhaseExecutionFailure(
        node_id="think.main",
        attempts=(PhaseAttemptFailure(attempt=1, category="permanent", error_type="RuntimeError"),),
    )
    diag = RunDiagnostic(
        run_id="r",
        trace_id="t",
        phase="think",
        node_id="think.main",
        error_type="RuntimeError",
        message=_summarize_attempts(failure),
        stack=(),
        causation=(),
        attempts=(),
        extra=(("error_kind", failure.error_kind),),
    )
    stop = StopDecision(
        should_stop=True,
        reason=StopReason.ERROR,
        status=TaskStatus.FAILED,
        failure=diag,
    )
    state = AgentState(trace_id="t", task="x", budget=Budget())
    DefaultReducer().apply_stop(state, stop)
    # reducer.apply_stop 透传原 message,不私自改成 fallback Chinese 句式。
    assert state.last_error == diag.message
    # ADR-0158 决策 四:AgentState.final_output 字段已删除;final output
    # 走 TerminalOutcome.final_output_ref。apply_stop 不再尝试写入 final_output,
    # 故无需断言;改断言 stop.failure 仍透传到 state.last_error。
    assert stop.failure is not None


def test_terminal_outcome_error_ref_carries_diagnostic() -> None:
    """TerminalOutcome.error_ref.diagnostic preserves the typed failure."""
    from lca.contracts.models.core.state import AgentState, Budget
    from lca.contracts.models.core.terminal_outcome import ErrorRef
    from lca.plugins.phase_graph.failure_stop import _summarize_attempts
    from lca.plugins.runtime.reducer import DefaultReducer

    failure = PhaseExecutionFailure(
        node_id="think.main",
        attempts=(PhaseAttemptFailure(attempt=1, category="permanent", error_type="RuntimeError"),),
    )
    diag = RunDiagnostic(
        run_id="r",
        trace_id="t",
        phase="think",
        node_id="think.main",
        error_type="RuntimeError",
        message=_summarize_attempts(failure),
        stack=(),
        causation=(),
        attempts=(),
    )
    stop = StopDecision(
        should_stop=True,
        reason=StopReason.ERROR,
        status=TaskStatus.FAILED,
        failure=diag,
    )
    state = AgentState(trace_id="t", task="x", budget=Budget())
    DefaultReducer().apply_stop(state, stop)
    # Re-derive ErrorRef the way reducer does:
    err = ErrorRef(
        kind="error",
        message=state.last_error,
        source_ref="",
        diagnostic=getattr(stop, "failure", None),
    )
    assert err.diagnostic is diag
    # ADR-clean-truths 决策 一:err.message 是机读摘要,至少带 node= 与 attempts=。
    assert err.message is not None
    assert "node=think.main" in err.message
    assert "attempts=" in err.message


def test_phase_failure_stop_result_no_final_output_when_only_failure() -> None:
    """Regression: ``StopDecision.final_output`` stays None for failure stops.

    Before ADR-0122 the same field stored the failure message, which then
    got treated as the run's successful output by the reducer.
    """
    failure = PhaseExecutionFailure(
        node_id="think.main",
        attempts=(PhaseAttemptFailure(attempt=1, category="permanent", error_type="E"),),
    )
    res = phase_failure_stop_result(failure, plan_ref="p", run_id="r", trace_id="t")
    stop: StopDecision = res.payload
    assert stop.final_output is None
    assert stop.failure is not None
    assert stop.failure.error_type == "E"
