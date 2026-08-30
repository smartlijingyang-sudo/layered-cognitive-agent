"""Build the standard terminal result for a typed exhausted phase failure."""

from __future__ import annotations

from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.stop import StopDecision, StopReason
from lca.contracts.protocols.command_envelope import RunDelta
from lca.contracts.protocols.declarative_execution import PhaseExecutionFailure, PhaseResult


def phase_failure_stop_result(
    failure: PhaseExecutionFailure,
    *,
    plan_ref: str,
) -> PhaseResult:
    """Safely converge a routable failed phase without exposing raw exception text."""

    stop = StopDecision(
        should_stop=True,
        reason=StopReason.ERROR,
        final_output=(
            "The agent could not complete a required "
            f"{failure.node_id} step after {len(failure.attempts)} attempt(s)."
        ),
        status=TaskStatus.FAILED,
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
