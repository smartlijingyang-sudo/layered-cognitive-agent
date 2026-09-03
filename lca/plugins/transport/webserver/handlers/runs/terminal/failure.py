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

    Also appends a durable line to ``traces/runs/<run_id>/kernel.log`` so
    ``lca-ops debug-run`` can surface the message when Journal is empty
    (ADR-0122 kernel.log intent / ADR-0165.1 carrier gap).
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
    _append_kernel_log(facts)


def _append_kernel_log(facts: RunFailureFacts) -> None:
    """Best-effort per-run kernel.log write; never raises into lifecycle."""
    try:
        from pathlib import Path

        from lca.infrastructure.observability.backends.run_locator_fs import (
            FilesystemRunLocator,
        )

        run_dir = Path("traces") / "runs" / facts.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        line = (
            f"run_failure_observed run_id={facts.run_id} "
            f"trace_id={facts.trace_id} error={facts.error}\n"
        )
        with FilesystemRunLocator(run_dir).kernel_log_path(facts.run_id).open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(line)
    except Exception:
        _log.debug(
            "kernel_log_append_failed",
            run_id=facts.run_id,
            exc_info=True,
        )


__all__ = ["RunFailureFacts", "record_run_failure"]
