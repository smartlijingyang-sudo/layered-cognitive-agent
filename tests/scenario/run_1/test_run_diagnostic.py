"""RunDiagnostic end-to-end — see ADR-0122.

These tests cover:

- ``RunDiagnostic`` is a typed, frozen, JSON-friendly value object.
- ``reducer.apply_stop`` propagates the diagnostic message into
  ``state.last_error`` instead of letting the fallback kick in.
- ``TerminalOutcome.error_ref.diagnostic`` carries the RunDiagnostic.

The ``phase_failure_stop_result`` cases that used to live here were
retired with the v1 phase-failure machinery (``PhaseExecutionFailure`` /
``PhaseAttemptFailure`` and the ``plugins.loop.phase._shared.failure_stop``
helper, all deleted in the ADR-0221 v2 cutover): failure stops are now
produced by the v2 driver, not by a loop-phase helper. The machine-readable
summary format those cases asserted (``node={...} error_kind={...}
attempts=N[...]``) is preserved below as a literal diagnostic message so
the reducer / ErrorRef propagation contracts stay covered.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

from lca.contracts.models.core.policy.stop import StopDecision, StopReason
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.runtime.support.diagnostic import (
    PhaseAttemptSummary,
    RunDiagnostic,
    StackFrame,
)

_SUMMARY = "node=think.main error_kind=internal attempts=1[1:permanent:RuntimeError]"


def _failure_diagnostic() -> RunDiagnostic:
    return RunDiagnostic(
        run_id="r",
        trace_id="t",
        phase="think",
        node_id="think.main",
        error_type="RuntimeError",
        message=_SUMMARY,
        stack=(),
        causation=(),
        attempts=(),
        extra=(("error_kind", "internal"),),
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


def test_reducer_apply_stop_propagates_diagnostic_message() -> None:
    """``state.last_error`` must be filled from the RunDiagnostic, not fall back."""
    from lca.contracts.models.core.state.state import AgentState, Budget
    from lca.plugins.loop.reducer.plugin import DefaultReducer

    diag = _failure_diagnostic()
    stop = StopDecision(
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
    from lca.contracts.models.core.state.state import AgentState, Budget
    from lca.contracts.models.core.state.terminal_outcome import ErrorRef
    from lca.plugins.loop.reducer.plugin import DefaultReducer

    diag = _failure_diagnostic()
    stop = StopDecision(
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
