"""Durable Session recovery — single authority path (ADR-0195 P4-S04)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from lca.contracts.harness.collaboration.agent import (
    ApprovalResumePoint,
    LiveAgentRecovery,
    LiveAgentStatus,
)
from lca.contracts.harness.tasks.session import SessionEvent
from lca.plugins.session.runtime.resume.resume_point import deserialize_resume_point


class SessionRecoveryError(ValueError):
    """Raised when Session facts cannot describe one unambiguous recovery state."""


class _RunStatusMutable(Protocol):
    status: object


def recover_live_agent(events: Iterable[SessionEvent]) -> LiveAgentRecovery:
    """Build the sole lifecycle recovery view from append-only Session facts."""
    completed_turns = 0
    checkpoint_status = LiveAgentStatus.IDLE
    pending: ApprovalResumePoint | None = None

    for event in events:
        if event.type == "turn.ended.v1":
            completed_turns = max(completed_turns, _turn(event))
        elif event.type == "session.checkpoint.v1":
            checkpoint_status = _checkpoint_status(event)
        elif event.type == "approval.persisted.v1":
            pending = _persisted_point(event)
        elif event.type == "approval.resolved.v1":
            pending = _resolve_pending(pending, event)

    if checkpoint_status is LiveAgentStatus.WAITING_INPUT:
        if pending is None:
            raise SessionRecoveryError(
                "waiting_input checkpoint requires one unresolved approval.persisted.v1 fact"
            )
        return LiveAgentRecovery(
            status=LiveAgentStatus.WAITING_INPUT,
            completed_turns=completed_turns,
            pending_resume=pending,
        )

    if checkpoint_status is LiveAgentStatus.DISPOSED:
        return LiveAgentRecovery(status=checkpoint_status, completed_turns=completed_turns)

    if pending is not None:
        raise SessionRecoveryError(
            "unresolved approval.persisted.v1 fact requires a waiting_input checkpoint"
        )

    return LiveAgentRecovery(status=checkpoint_status, completed_turns=completed_turns)


def recovery_from_events(events: Iterable[SessionEvent]) -> LiveAgentRecovery:
    return recover_live_agent(events)


def sync_run_status_from_recovery(session: _RunStatusMutable, recovery: LiveAgentRecovery) -> None:
    from lca.contracts.observability.registry.status import RunLifecycleStatus

    status_map = {
        LiveAgentStatus.IDLE: RunLifecycleStatus.COMPLETED,
        LiveAgentStatus.WAITING_INPUT: RunLifecycleStatus.WAITING_INPUT,
        LiveAgentStatus.DISPOSED: RunLifecycleStatus.CANCELED,
    }
    mapped = status_map.get(recovery.status)
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
    recovery = recovery_from_events(events)
    sync_run_status_from_recovery(session, recovery)
    if recovery.status is not LiveAgentStatus.WAITING_INPUT:
        raise SessionRecoveryError(
            f"transport resume requires waiting_input recovery view, got {recovery.status!s}"
        )
    if recovery.pending_resume is None:
        raise SessionRecoveryError("waiting_input recovery requires pending_resume")


def _turn(event: SessionEvent) -> int:
    value = event.data.get("turn")
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SessionRecoveryError("turn.ended.v1 requires a non-negative integer turn")
    return value


def _checkpoint_status(event: SessionEvent) -> LiveAgentStatus:
    raw = str(event.data.get("status") or "")
    legacy_terminal = {
        "completed": LiveAgentStatus.IDLE,
        "failed": LiveAgentStatus.IDLE,
        "canceled": LiveAgentStatus.DISPOSED,
    }
    if raw in legacy_terminal:
        return legacy_terminal[raw]
    try:
        status = LiveAgentStatus(raw)
    except ValueError as exc:
        raise SessionRecoveryError(
            f"session.checkpoint.v1 has unsupported LiveAgent status: {raw!r}"
        ) from exc
    if status is LiveAgentStatus.WORKING:
        raise SessionRecoveryError("working state must not be checkpointed")
    return status


def _persisted_point(event: SessionEvent) -> ApprovalResumePoint:
    payload = event.data.get("resume_point")
    if not isinstance(payload, dict):
        raise SessionRecoveryError("approval.persisted.v1 requires a resume_point mapping")
    point = deserialize_resume_point(payload)
    approval_id = event.data.get("approval_id")
    if approval_id != point.approval_id:
        raise SessionRecoveryError("approval.persisted.v1 approval_id must match resume_point")
    return point


def _resolve_pending(
    pending: ApprovalResumePoint | None,
    event: SessionEvent,
) -> ApprovalResumePoint | None:
    approval_id = event.data.get("approval_id")
    if pending is None:
        raise SessionRecoveryError("approval.resolved.v1 has no persisted approval to resolve")
    if approval_id != pending.approval_id:
        raise SessionRecoveryError("approval.resolved.v1 does not match the pending approval")
    approved = event.data.get("approved")
    if not isinstance(approved, bool):
        raise SessionRecoveryError("approval.resolved.v1 requires a boolean approved flag")
    return None


__all__ = [
    "SessionRecoveryError",
    "append_approval_resolved_if_pending",
    "assert_resume_allowed",
    "recover_live_agent",
    "recovery_from_events",
    "sync_run_status_from_recovery",
]
