"""Apply execution outcomes to the carrier-facing run state.

This module owns the translation from driver/task result vocabulary to
``RunSession`` state.  It deliberately does not schedule work, persist facts,
or terminalize a run; those concerns belong to the lifecycle coordinator and
its collaborators.
"""

from __future__ import annotations

from typing import Any

from lca.contracts.models.core.lifecycle import TaskStatus
from lca.plugins.transport.webserver.handlers.runs.execute.loop_drivers import DriverOutcome
from lca.plugins.transport.webserver.handlers.runs.observability.error_presentation import (
    format_user_error,
)
from lca.plugins.transport.webserver.handlers.runs.session.session import RunSession, RunStatus


class RunOutcomeApplier:
    """Translate one execution result into the legacy session projection."""

    def apply_driver(self, session: RunSession, outcome: DriverOutcome) -> bool:
        """Apply a driver outcome and return whether the run is paused."""

        if outcome.waiting_input:
            session.status = RunStatus.WAITING_INPUT
            session.snapshot = outcome.snapshot
            session.runnable = outcome.resumable
            session.approval_request = outcome.approval_request
            return True

        if not outcome.success and not session.error and outcome.error:
            session.error = format_user_error(
                outcome.error,
                run_id=session.run_id,
                trace_id=session.trace_id,
            )
        return False

    def apply_resume(self, session: RunSession, result: Any) -> bool:
        """Apply a resumable task result and return whether it needs input again."""

        if result.status == TaskStatus.INPUT_REQUIRED:
            session.status = RunStatus.WAITING_INPUT
            session.snapshot = result.extra.get("state_snapshot")
            session.approval_request = result.extra.get("approval_request")
            return True

        if result.status != TaskStatus.COMPLETED and not session.error and result.error:
            session.error = format_user_error(
                result.error,
                run_id=session.run_id,
                trace_id=session.trace_id,
            )
        return False


__all__ = ["RunOutcomeApplier"]
