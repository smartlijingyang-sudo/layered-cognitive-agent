"""Fold durable Session Spine facts into one LiveAgent recovery view."""

from __future__ import annotations

from collections.abc import Iterable

from lca.contracts.harness.collaboration.agent import (
    ApprovalResumePoint,
    LiveAgentRecovery,
    LiveAgentStatus,
)
from lca.contracts.harness.tasks.session import SessionEvent
from lca.plugins.session.runtime.resume_point import deserialize_resume_point


class SessionRecoveryError(ValueError):
    """Raised when Session facts cannot describe one unambiguous recovery state."""


def recover_live_agent(events: Iterable[SessionEvent]) -> LiveAgentRecovery:
    """Build the sole lifecycle recovery view from append-only Session facts.

    A pending approval remains valid only when its persisted point is the latest
    unresolved approval fact. This keeps recovery independent of a registry's
    process-local cache and of any previous LiveAgent implementation.
    """

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

    # A canceled Session invalidates any outstanding approval.  The approval
    # fact remains in the append-only Journal for audit, while the terminal
    # checkpoint is the sole recovery authority for its live lifecycle.
    if checkpoint_status is LiveAgentStatus.DISPOSED:
        return LiveAgentRecovery(status=checkpoint_status, completed_turns=completed_turns)

    if pending is not None:
        raise SessionRecoveryError(
            "unresolved approval.persisted.v1 fact requires a waiting_input checkpoint"
        )

    return LiveAgentRecovery(status=checkpoint_status, completed_turns=completed_turns)


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


__all__ = ["SessionRecoveryError", "recover_live_agent"]
