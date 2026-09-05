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
            message=attempt.error_message or None,
        )
        for attempt in failure.attempts
    )


def _summarize_attempts(failure: PhaseExecutionFailure) -> str:
    """Compact machine-readable summary of all attempts.

    ADR-clean-truths 决策 一:替代原 ``The agent could not complete a required
    {node_id} step after {n} attempt(s).`` 文学化句式。格式固定为
    ``node={node_id} error_kind={error_kind} attempts={n}[cat:type,…]``,
    便于 UI / LobeHub / run-doctor 直接按字段解析,不再被英文长句绑死。
    上游错误原文不在此函数里;``phase_failure_stop_result`` 在摘要后追加
    `` | {root_cause}`` 后缀(见 :func:`_root_cause_message`)。
    """
    categories = ",".join(f"{a.attempt}:{a.category}:{a.error_type}" for a in failure.attempts)
    return (
        f"node={failure.node_id} "
        f"error_kind={failure.error_kind} "
        f"attempts={len(failure.attempts)}"
        f"[{categories}]"
    )


def _root_cause_message(failure: PhaseExecutionFailure) -> str:
    """Latest captured upstream error text across attempts ("" = none).

    多次 attempt 时取最后一次携带原文的——它是终态根因。原文由
    ``PhaseExecutionRunner`` 在捕获点做有界/单行归一化,这里只做选取。
    """
    for attempt in reversed(failure.attempts):
        if attempt.error_message:
            return attempt.error_message
    return ""


def _failure_message(failure: PhaseExecutionFailure) -> str:
    """Machine label plus upstream root cause when captured.

    展示串同时携带"解释"(机读分类)与"根源"(上游错误原文,如
    ``Client error '429 Too Many Requests' for url '…'``),reducer 透传后
    直达 TerminalOutcome.error_ref / Result.error / 前端 error 字段。
    """
    label = _summarize_attempts(failure)
    root_cause = _root_cause_message(failure)
    return f"{label} | {root_cause}" if root_cause else label


def phase_failure_stop_result(
    failure: PhaseExecutionFailure,
    *,
    plan_ref: str,
    run_id: str = "",
    trace_id: str = "",
    suggested_action: str | None = None,
) -> PhaseResult:
    """Converge a routable failed phase with a typed, display-ready failure.

    ADR-0122: instead of overloading ``StopDecision.final_output`` with a
    failure summary string (which previously collapsed into a generic
    Chinese fallback when ``state.last_error`` was empty), emit a typed
    :class:`RunDiagnostic` and bind it to ``StopDecision.failure``. The
    reducer then reads ``failure.message`` / ``failure.attempts`` directly
    rather than scanning a string.

    ADR-clean-truths 决策 一:``message`` 是机读摘要(节点+错误分类+attempts);
    捕获到上游错误原文时追加 `` | {root_cause}`` 后缀,使前端 / debug-run
    同时看到分类解释与根源(如 provider 429 文案)。UI / LobeHub 优先读
    ``error_kind`` 字段做结构化展示,后缀只影响人读 ``error`` 文本。
    """
    attempts = _attempts_to_summaries(failure)
    last = failure.attempts[-1] if failure.attempts else None
    diagnostic = RunDiagnostic(
        run_id=run_id,
        trace_id=trace_id,
        phase="stop",
        node_id=failure.node_id,
        error_type=last.error_type if last is not None else "UnknownError",
        message=_failure_message(failure),
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
