"""Deep run lifecycle coordination and terminalization (INV-ARCH-01, INV-ARCH-02).

Consolidates driver/resume outcome translation, status derivation, failure logging,
and terminal transition closure behind a single cohesive seam.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.observability.infra.close_barrier import CloseReason
from lca.contracts.observability.registry.status import RunLifecycleStatus
from lca.contracts.observability.run_live import LiveTerminalHint
from lca.infrastructure.tools.run.finalizer import finalize_run
from lca.plugins.transport.webserver.carrier.runs.execute.loop_drivers import DriverOutcome
from lca.plugins.transport.webserver.carrier.runs.lifecycle.export_disposal import (
    dispose_export as _dispose_export,
)
from lca.plugins.transport.webserver.handlers.runs.session.session.session import (
    RunRegistry,
    RunSession,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.failure import (
    RunFailureFacts,
    record_run_failure,
)
from lca.plugins.transport.webserver.read.runs.terminal import (
    record_terminal_materialization as _record_terminal_materialization,
)

_log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Status derivation helpers
# ---------------------------------------------------------------------------


def task_cancelled(task: object) -> bool:
    """Return whether a task object has cancellation pending or delivered."""
    return isinstance(task, asyncio.Task) and (task.cancelled() or task.cancelling() > 0)


def current_task_cancelled() -> bool:
    """Return whether the terminalization task has cancellation pending or delivered."""
    return task_cancelled(asyncio.current_task())


def derive_terminal_status(session: RunSession, success: bool) -> None:
    """Derive terminal status: cancellation / errors / carrier fallback."""
    if session.cancel_requested or task_cancelled(session.task) or current_task_cancelled():
        session.cancel_requested = True
        session.status = RunLifecycleStatus.CANCELLED
    else:
        fallback_terminal_status(session, success)
    if session.status in {
        RunLifecycleStatus.CANCELLED,
        RunLifecycleStatus.FAILED,
        RunLifecycleStatus.COMPLETED,
    }:
        session.closed_at = time.time()


def fallback_terminal_status(session: RunSession, success: bool) -> None:
    """Retain the carrier fallback when Session fold has not yet observed a root terminal fact."""
    if session.error:
        session.status = RunLifecycleStatus.FAILED
    elif success:
        session.status = RunLifecycleStatus.COMPLETED
    else:
        session.status = RunLifecycleStatus.FAILED


def resolve_live_terminal_hint_dto(session: RunSession) -> LiveTerminalHint:
    """Structured terminal hint for the run live observe seam."""
    status = session.status.value if hasattr(session.status, "value") else str(session.status)
    return LiveTerminalHint(status, session.error or "")


# ---------------------------------------------------------------------------
# History persistence helper
# ---------------------------------------------------------------------------


def _maybe_append_conversation_log(session: RunSession, success: bool) -> None:
    """Best-effort cross-run history persistence."""
    if not success:
        return
    try:
        from lca.infrastructure.path.locator import get_lca_home
        from lca.plugins.transport.webserver.handlers.runs.session.message.conversation_log import (
            append_conversation_turn,
        )

        assistant_id = getattr(session, "assistant_id", "")
        topic_id = getattr(session, "topic_id", "")
        if not isinstance(assistant_id, str) or not assistant_id:
            return
        if not isinstance(topic_id, str) or not topic_id:
            return
        user_text = getattr(session, "user_text", "")
        assistant_text = getattr(session, "output", "")
        if not isinstance(user_text, str) or not user_text.strip():
            return
        if not isinstance(assistant_text, str) or not assistant_text.strip():
            return
        append_conversation_turn(
            assistant_home=get_lca_home() / "assistants" / assistant_id,
            topic_id=topic_id,
            user_text=user_text.strip(),
            assistant_text=assistant_text.strip(),
        )
    except Exception:
        _log.exception(
            "conversation_log.append_failed",
            run_id=getattr(session, "run_id", "?"),
        )


# ---------------------------------------------------------------------------
# Unified RunTerminalCoordinator
# ---------------------------------------------------------------------------


class RunTerminalCoordinator:
    """Deep module coordinating outcome translation, status transitions, and terminalization."""

    def __init__(
        self,
        registry: RunRegistry | None = None,
        *,
        finalizer: Callable[[str], Awaitable[None]] = finalize_run,
        materializer: Callable[[RunSession], None] | None = None,
    ) -> None:
        self._registry = registry
        self._finalizer = finalizer
        self._materializer = materializer or _record_terminal_materialization

    # --- Outcome translation ---

    def apply_driver_outcome(self, session: RunSession, outcome: DriverOutcome) -> bool:
        """Apply a driver outcome and return whether the run is paused."""
        if outcome.waiting_input:
            session.status = RunLifecycleStatus.WAITING_INPUT
            session.snapshot = outcome.snapshot
            session.runnable = outcome.resumable
            session.approval_request = outcome.approval_request
            return True
        return False

    apply_driver = apply_driver_outcome

    def apply_resume_outcome(self, session: RunSession, result: Any) -> bool:
        """Apply a resumable task result and return whether it needs input again."""
        if getattr(result, "status", None) == TaskStatus.INPUT_REQUIRED:
            session.status = RunLifecycleStatus.WAITING_INPUT
            extra = getattr(result, "extra", {}) or {}
            session.snapshot = extra.get("state_snapshot")
            session.approval_request = extra.get("approval_request")
            return True
        return False

    apply_resume = apply_resume_outcome

    # --- Failure recording ---

    def record_failure(self, facts: RunFailureFacts) -> None:
        """Record defensive failure log without Journal emission."""
        record_run_failure(facts)

    # --- Status derivation ---

    def derive_status(self, session: RunSession, success: bool) -> None:
        """Derive terminal status for session."""
        derive_terminal_status(session, success)

    # --- Terminalization ---

    async def terminalize(self, session: RunSession, *, success: bool) -> None:
        """Close a run exactly once while preserving terminal facts and cleaning resources."""
        close_reason: CloseReason = "completed" if success else "error"
        try:
            from lca.plugins.transport.webserver.handlers.runs.terminal.observation import (
                ensure_carrier_terminal_observation,
            )

            derive_terminal_status(session, success)
            ensure_carrier_terminal_observation(session)
            res = self._finalizer(session.run_id)
            if inspect.isawaitable(res):
                await res
        except Exception:
            _log.exception("finalize_run_pre_close_failed", hop="H2", run_id=session.run_id)
        finally:
            try:
                if session.hub is not None:
                    session.hub.close()
            finally:
                if self._registry is not None:
                    self._registry.clear_inflight(session.run_id)
                    self._registry.prune()
                _maybe_append_conversation_log(session, success)
                self._materializer(session)
                if session.hub is not None:
                    await _dispose_export(session.hub)
                try:
                    released = session.close(close_reason)
                    if not released:
                        _log.debug(
                            "run_session_already_closed",
                            run_id=session.run_id,
                        )
                except Exception:
                    _log.exception(
                        "run_session_close_token_reset_failed",
                        run_id=session.run_id,
                    )


# Backward-compatible aliases within this package
RunTerminalizer = RunTerminalCoordinator
RunOutcomeApplier = RunTerminalCoordinator

__all__ = [
    "RunFailureFacts",
    "RunOutcomeApplier",
    "RunTerminalCoordinator",
    "RunTerminalizer",
    "current_task_cancelled",
    "derive_terminal_status",
    "fallback_terminal_status",
    "record_run_failure",
    "resolve_live_terminal_hint_dto",
    "task_cancelled",
]
