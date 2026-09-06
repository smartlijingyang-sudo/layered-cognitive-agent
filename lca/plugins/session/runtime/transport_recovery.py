"""Transport-facing recovery helpers (ADR-0191 Wave B3)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from lca.contracts.harness.collaboration.agent import LiveAgentRecovery, LiveAgentStatus
from lca.contracts.harness.tasks.session import SessionEvent
from lca.plugins.session.runtime.recovery import SessionRecoveryError, recover_live_agent
from lca.plugins.transport.webserver.handlers.runs.session.session import RunStatus


class _RunStatusMutable(Protocol):
    status: RunStatus

_STATUS_MAP: dict[LiveAgentStatus, RunStatus] = {
    LiveAgentStatus.IDLE: RunStatus.COMPLETED,
    LiveAgentStatus.WAITING_INPUT: RunStatus.WAITING_INPUT,
    LiveAgentStatus.DISPOSED: RunStatus.CANCELED,
}


def recovery_from_events(events: Iterable[SessionEvent]) -> LiveAgentRecovery:
    """Fold Session facts into the durable recovery view."""
    return recover_live_agent(events)


def sync_run_status_from_recovery(session: _RunStatusMutable, recovery: LiveAgentRecovery) -> None:
    """Align legacy RunSession.status with Session-fact recovery authority."""
    mapped = _STATUS_MAP.get(recovery.status)
    if mapped is not None:
        session.status = mapped


def append_approval_resolved_if_pending(
    session_writer: object,
    events: Iterable[SessionEvent],
    *,
    approval_id: str,
    payload: str,
    command_id: str,
) -> bool:
    """Append ``approval.resolved.v1`` when recovery still shows an open approval."""
    recovery = recovery_from_events(events)
    if recovery.pending_resume is None:
        return False
    pending_id = recovery.pending_resume.approval_id
    if approval_id and approval_id != pending_id:
        return False
    append = getattr(session_writer, "append", None)
    if not callable(append):
        return False
    append(
        "approval.resolved.v1",
        {
            "approval_id": pending_id,
            "command_id": command_id,
            "payload": payload,
            "approved": True,
        },
        visibility="internal",
    )
    return True


def assert_resume_allowed(session: _RunStatusMutable, events: Iterable[SessionEvent]) -> None:
    """Fail-closed when Session facts disagree with transport resume preconditions."""
    recovery = recovery_from_events(events)
    sync_run_status_from_recovery(session, recovery)
    if recovery.status is not LiveAgentStatus.WAITING_INPUT:
        raise SessionRecoveryError(
            f"transport resume requires waiting_input recovery view, got {recovery.status!s}"
        )
    if recovery.pending_resume is None:
        raise SessionRecoveryError("waiting_input recovery requires pending_resume")


__all__ = [
    "append_approval_resolved_if_pending",
    "assert_resume_allowed",
    "recovery_from_events",
    "sync_run_status_from_recovery",
]
