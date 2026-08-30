"""Best-effort recording of run failure facts.

This module owns Journal observation only.  It deliberately accepts a small,
immutable fact value instead of the mutable ``RunSession`` carrier so that
lifecycle transitions and observability have separate ownership.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import structlog

from lca.contracts.atoms.ids import RunId, TraceId
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.observability.journal import AgentRunFinished, AgentRunStarted, RunScope
from lca.layer0_infra.observability import bind_backends, record, run_scope

_log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RunFailureFacts:
    """The minimum immutable data required to append a failed-run fact."""

    trace_id: str
    run_id: str
    agent_role: str
    strategy_key: str
    objective: str
    error: str
    hub: Any


def record_run_failure(facts: RunFailureFacts) -> None:
    """Append failure facts without changing the caller's lifecycle outcome.

    Failure reporting is best-effort observability.  A reporting failure must
    not mask the original execution error or alter the lifecycle state chosen
    by the caller.
    """

    if facts.hub is None:
        return
    try:
        with (
            bind_backends(facts.hub),
            run_scope(
                RunScope(
                    trace_id=cast("TraceId", facts.trace_id),
                    run_id=cast("RunId", facts.run_id),
                )
            ),
        ):
            record(
                AgentRunStarted(
                    agent_role=facts.agent_role,
                    strategy_key=facts.strategy_key,
                    objective=facts.objective,
                    objective_preview=facts.objective[:200],
                    from_role="",
                )
            )
            record(
                AgentRunFinished(
                    status=TaskStatus.FAILED.value,
                    output_text="",
                    steps=0,
                    error=facts.error,
                )
            )
    except Exception:
        _log.warning("run_failure_journal_failed", run_id=facts.run_id, exc_info=True)


__all__ = ["RunFailureFacts", "record_run_failure"]
