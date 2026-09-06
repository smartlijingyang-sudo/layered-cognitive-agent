"""Derive legacy Gateway terminal status from cancellation, errors, and Journal facts."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from lca.contracts.observability.registry.status import RunLifecycleStatus
from lca.infrastructure.observability import BoundObservability, fold_run_state
from lca.plugins.transport.webserver.handlers.runs.session.session.session import RunSession


def journal_store(hub: BoundObservability | None) -> Any:
    """Extract the run store from a bound journal, if one is present."""
    if hub is None or hub.journal is None:
        return None
    return getattr(hub.journal, "store", hub.journal)


def task_cancelled(task: object) -> bool:
    """Return whether a task object has cancellation pending or delivered."""
    return isinstance(task, asyncio.Task) and (task.cancelled() or task.cancelling() > 0)


def current_task_cancelled() -> bool:
    """Return whether the terminalization task has cancellation pending or delivered."""
    return task_cancelled(asyncio.current_task())


def derive_terminal_status(session: RunSession, success: bool) -> None:
    """Derive terminal status and error from Journal facts, then carrier fallback."""
    if session.cancel_requested or task_cancelled(session.task) or current_task_cancelled():
        session.cancel_requested = True
        session.status = RunLifecycleStatus.CANCELED
    elif session.hub is not None:
        store = journal_store(session.hub)
        if store is None:
            fallback_terminal_status(session, success)
        else:
            folded = fold_run_state(store.events)
            session.status = folded.status
            if folded.error:
                session.error = folded.error
            if session.status is RunLifecycleStatus.RUNNING:
                fallback_terminal_status(session, success)
    else:
        fallback_terminal_status(session, success)
    if session.status in {
        RunLifecycleStatus.CANCELED,
        RunLifecycleStatus.FAILED,
        RunLifecycleStatus.COMPLETED,
    }:
        session.closed_at = time.time()


def fallback_terminal_status(session: RunSession, success: bool) -> None:
    """Retain the carrier fallback when the Journal cannot derive a terminal state."""
    if session.error:
        session.status = RunLifecycleStatus.FAILED
    elif success:
        session.status = RunLifecycleStatus.COMPLETED
    else:
        session.status = RunLifecycleStatus.FAILED


__all__ = [
    "current_task_cancelled",
    "derive_terminal_status",
    "fallback_terminal_status",
    "journal_store",
    "task_cancelled",
]
