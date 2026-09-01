"""Best-effort logging of run failure (no Journal emission).

This module is a pure observation-safety net: when the normal lifecycle
finishing path itself fails, log the failure fact so operators can see it,
but do NOT emit ``AgentRunFinished`` into the Journal. The
``AgentRunStarted`` / ``AgentRunFinished`` facts are owned by
``lca.agent.cognitive_agent`` (catalog single-emitter constraint); this
handler is not allowed to bypass that ownership. If the agent's own
termination path failed, the prior ``AgentRunFinished`` event is still in
the Journal store and UI终止卡 can fall back to it.

Accepting a small immutable fact value (rather than the mutable
``RunSession`` carrier) keeps lifecycle and observability ownership separate.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

_log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RunFailureFacts:
    """The minimum immutable data describing a failed run for logging."""

    trace_id: str
    run_id: str
    agent_role: str
    strategy_key: str
    objective: str
    error: str
    hub: object | None = None


def record_run_failure(facts: RunFailureFacts) -> None:
    """Log the failure fact; never emit a Journal event.

    Lifecycle and Journal emission are owned by ``lca.agent.cognitive_agent``.
    This function is a defensive log so the failure is visible when the
    primary emission path itself failed.
    """
    _log.warning(
        "run_failure_observed",
        trace_id=facts.trace_id,
        run_id=facts.run_id,
        agent_role=facts.agent_role,
        strategy_key=facts.strategy_key,
        objective_preview=facts.objective[:200],
        error=facts.error,
    )


__all__ = ["RunFailureFacts", "record_run_failure"]
