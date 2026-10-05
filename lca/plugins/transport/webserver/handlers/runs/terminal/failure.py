"""Best-effort logging of run failure (no Journal emission).

Defensive observation safety net: logs the failure fact and writes kernel.log,
strictly decoupled from the mutable RunSession lifecycle carrier.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from lca.infrastructure.observability.spine.sinks.naming import kernel_log_filename
from lca.infrastructure.persistence.run_paths import default_runs_root, ensure_run_dir

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
    """Log the failure fact and append to kernel.log without Journal emission."""
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
        run_dir = ensure_run_dir(default_runs_root() / facts.run_id)
        line = (
            f"run_failure_observed run_id={facts.run_id} "
            f"trace_id={facts.trace_id} error={facts.error}\n"
        )
        with (run_dir / kernel_log_filename(facts.run_id)).open("a", encoding="utf-8") as handle:
            handle.write(line)
    except Exception:
        _log.debug(
            "kernel_log_append_failed",
            run_id=facts.run_id,
            exc_info=True,
        )


__all__ = ["RunFailureFacts", "record_run_failure"]
