"""Build the standard terminal result for a typed exhausted phase failure."""

from __future__ import annotations

from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.stop import StopDecision, StopReason
from lca.contracts.protocols.act.command_envelope import RunDelta
from lca.contracts.protocols.declarative.declarative_execution import (
    PhaseExecutionFailure,
    PhaseResult,
)
from lca.runtime.diagnostic import PhaseAttemptSummary, RunDiagnostic


def _attempts_to_summaries(failure: PhaseExecutionFailure) -> tuple[PhaseAttemptSummary, ...]:
    """Translate PhaseExecutionFailure.attempts into typed summaries.

    ADR-0122: preserve attempt history all the way to StopDecision.failure.
    """
    return tuple(
        PhaseAttemptSummary(
            attempt=attempt.attempt,
            category=attempt.category,
            error_type=attempt.error_type,
        )
        for attempt in failure.attempts
    )


def _summarize_attempts(failure: PhaseExecutionFailure) -> str:
    """Compact machine-readable summary of all attempts.

    ADR-clean-truths 决策 一:替代原 ``The agent could not complete a required
    {node_id} step after {n} attempt(s).`` 文学化句式。格式固定为
    ``node={node_id} error_kind={error_kind} attempts={n}[cat:type,…]``,
    便于 UI / LobeHub / run-doctor 直接按字段解析,不再被英文长句绑死。
    categories = ",".join(
        f"{a.attempt}:{a.category}:{a.error_type}" for a in failure.attempts
    )
    return (
        f"node={failure.node_id} "
        f"error_kind={failure.error_kind} "
        f"attempts={len(failure.attempts)}"
        f"[{categories}]"
    )


def phase_failure_stop_result(
    failure: PhaseExecutionFailure,
    *,
    plan_ref: str,
    run_id: str = "",
    trace_id: str = "",
    suggested_action: str | None = None,
) -> PhaseResult:
    """Safely converge a routable failed phase without exposing raw exception text.

    ADR-0122: instead of overloading ``StopDecision.final_output`` with a
    failure summary string (which previously collapsed into a generic
    Chinese fallback when ``state.last_error`` was empty), emit a typed
    :class:`RunDiagnostic` and bind it to ``StopDecision.failure``. The
    reducer then reads ``failure.message`` / ``failure.attempts`` directly
    rather than scanning a string.

    ADR-clean-truths 决策 一:``message`` 现在是机读摘要(节点+错误分类+attempts),
    UI / LobeHub 优先读 ``error_kind`` 字段做展示,不再依赖自由文本。
    """
    attempts = _attempts_to_summaries(failure)
    last = failure.attempts[-1] if failure.attempts else None
    diagnostic = RunDiagnostic(
        run_id=run_id,
        trace_id=trace_id,
        phase="stop",
        node_id=failure.node_id,
        error_type=last.error_type if last is not None else "UnknownError",
        message=_summarize_attempts(failure),
        stack=(),
        causation=(),
        attempts=attempts,
        suggested_action=suggested_action,
        extra=(("error_kind", failure.error_kind),),
    )
    stop = StopDecision(
        should_stop=True,
        reason=StopReason.ERROR,
        status=TaskStatus.FAILED,
        failure=diagnostic,
    )
    return PhaseResult(
        result_kind="stop_decision",
        payload=stop,
        deltas=(
            RunDelta(
                plan_ref=plan_ref,
                metadata={"operation": "stop", "stop": stop},
            ),
        ),
    )


__all__ = ["phase_failure_stop_result"]
