"""Pure Session Spine lifecycle mappings used by LiveAgent adapters."""

from __future__ import annotations

from collections.abc import Mapping

from lca.contracts.harness.agent import ApprovalResumePoint, LiveAgentStatus
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.harness.session.resume_point import resume_point_from_state_snapshot


def status_from_task(status: TaskStatus | object | None) -> LiveAgentStatus:
    """Map a runtime result status onto the small live-agent lifecycle vocabulary."""

    if status == TaskStatus.INPUT_REQUIRED:
        return LiveAgentStatus.WAITING_INPUT
    if status == TaskStatus.CANCELED:
        return LiveAgentStatus.DISPOSED
    if status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
        return LiveAgentStatus.IDLE
    return LiveAgentStatus.WORKING


def resume_point_from_result(result: object) -> ApprovalResumePoint:
    """Read the durable approval resume point required by a waiting result."""

    extra = getattr(result, "extra", None)
    if not isinstance(extra, Mapping):
        raise ValueError("waiting input result requires terminal resume metadata")
    resume_cursor = extra.get("resume_cursor")
    snapshot = extra.get("state_snapshot")
    if not isinstance(resume_cursor, Mapping):
        raise ValueError("waiting input result requires a durable resume_cursor")
    approval_id = resume_cursor.get("approval_id")
    if not isinstance(approval_id, str) or not approval_id.strip():
        raise ValueError("waiting input result requires a non-empty approval_id")
    return resume_point_from_state_snapshot(approval_id, snapshot)


def state_ref_from_result(result: object) -> str | None:
    """Extract a durable final state reference without accepting empty values."""

    state_ref = getattr(result, "final_state_ref", None)
    return state_ref if isinstance(state_ref, str) and state_ref else None


def checkpoint_status(status: object, live_status: LiveAgentStatus) -> str:
    """Project runtime and live statuses into the durable checkpoint vocabulary."""

    if status == TaskStatus.COMPLETED:
        return "completed"
    if status == TaskStatus.FAILED:
        return "failed"
    if live_status is LiveAgentStatus.DISPOSED:
        return "canceled"
    return live_status.value


def turn_end_reason(status: object, live_status: LiveAgentStatus) -> str:
    """Project runtime and live statuses into the durable Turn outcome vocabulary."""

    if live_status is LiveAgentStatus.WAITING_INPUT:
        return "waiting_input"
    if status == TaskStatus.FAILED:
        return "error"
    if live_status is LiveAgentStatus.DISPOSED:
        return "canceled"
    return "completed"


__all__ = [
    "checkpoint_status",
    "resume_point_from_result",
    "state_ref_from_result",
    "status_from_task",
    "turn_end_reason",
]
