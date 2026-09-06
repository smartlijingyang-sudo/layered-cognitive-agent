"""Apply execution outcomes to the carrier-facing run state.

This module owns the translation from driver/task result vocabulary to
``RunSession`` state.  It deliberately does not schedule work, persist facts,
or terminalize a run; those concerns belong to the lifecycle coordinator and
its collaborators.
"""

from __future__ import annotations

from typing import Any

from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.observability.registry.status import RunLifecycleStatus
from lca.plugins.transport.webserver.carrier.runs.execute.loop_drivers import DriverOutcome
from lca.plugins.transport.webserver.handlers.runs.session.session.session import RunSession


class RunOutcomeApplier:
    """Translate one execution result into the legacy session projection."""

    def apply_driver(self, session: RunSession, outcome: DriverOutcome) -> bool:
        """Apply a driver outcome and return whether the run is paused."""

        if outcome.waiting_input:
            session.status = RunLifecycleStatus.WAITING_INPUT
            # P3-06: cache live handles for hot resume; not durable authority.
            session.snapshot = outcome.snapshot
            session.runnable = outcome.resumable
            session.approval_request = outcome.approval_request
            return True
        return False

    def apply_resume(self, session: RunSession, result: Any) -> bool:
        """Apply a resumable task result and return whether it needs input again."""

        if result.status == TaskStatus.INPUT_REQUIRED:
            session.status = RunLifecycleStatus.WAITING_INPUT
            session.snapshot = result.extra.get("state_snapshot")
            session.approval_request = result.extra.get("approval_request")
            return True
        return False


__all__ = ["RunOutcomeApplier"]
