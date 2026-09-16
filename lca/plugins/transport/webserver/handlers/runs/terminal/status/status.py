"""Derive Gateway terminal status from cancellation, errors, and Session facts.

ADR-0195 O6 + ADR-0186:facts 走 ``Session.append``(<run_id>.spine.jsonl)
单一 SSOT;journal store 不再保留。
"""

from __future__ import annotations

import asyncio
import time

from lca.contracts.observability.registry.status import RunLifecycleStatus
from lca.contracts.observability.run_live import LiveTerminalHint
from lca.plugins.transport.webserver.handlers.runs.session.session.session import RunSession


def task_cancelled(task: object) -> bool:
    """Return whether a task object has cancellation pending or delivered."""
    return isinstance(task, asyncio.Task) and (task.cancelled() or task.cancelling() > 0)


def current_task_cancelled() -> bool:
    """Return whether the terminalization task has cancellation pending or delivered."""
    return task_cancelled(asyncio.current_task())


def derive_terminal_status(session: RunSession, success: bool) -> None:
    """Derive terminal status: cancellation / errors / carrier fallback (Session is SSOT)."""
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


def resolve_live_terminal_hint(session: RunSession) -> tuple[str, str]:
    """Return the terminal status/error hint for live SSE synthetic ``done``.

    Session fold is SSOT (ADR-0186). Carrier ``RunSession`` fields are the
    fallback when fold has not yet observed a root terminal fact — typical
    during terminalize or when the live subscriber reconnects after hub close.
    """
    return resolve_live_terminal_hint_dto(session).as_tuple()


def resolve_live_terminal_hint_dto(session: RunSession) -> LiveTerminalHint:
    """Structured terminal hint for the run live observe seam."""
    status = session.status.value if hasattr(session.status, "value") else str(session.status)
    return LiveTerminalHint(status, session.error or "")


__all__ = [
    "current_task_cancelled",
    "derive_terminal_status",
    "fallback_terminal_status",
    "resolve_live_terminal_hint",
    "resolve_live_terminal_hint_dto",
    "task_cancelled",
]
