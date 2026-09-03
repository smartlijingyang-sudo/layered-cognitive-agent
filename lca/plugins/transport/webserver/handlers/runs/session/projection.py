"""Carrier-facing projections for one retained run session.

This module owns translation from the mutable ``RunSession`` model to the
small, stable payload consumed by legacy gateway query paths.  The registry
retains sessions; it does not know the carrier payload schema.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lca.contracts.observability.status import RunLifecycleStatus

if TYPE_CHECKING:
    from lca.plugins.transport.webserver.handlers.runs.session.session import RunSession

_LOBEHUB_STATUS_MAP: dict[RunLifecycleStatus, str] = {
    RunLifecycleStatus.PENDING: "running",
    RunLifecycleStatus.RUNNING: "running",
    RunLifecycleStatus.WAITING_INPUT: "waiting_input",
    RunLifecycleStatus.COMPLETED: "completed",
    RunLifecycleStatus.FAILED: "error",
    RunLifecycleStatus.CANCELLED: "interrupted",
}


def to_lobehub_session_status(status: RunLifecycleStatus) -> str:
    """Project the run lifecycle status onto the LobeHub session wire value.

    只覆盖 session 当前可达的状态值;PAUSED / TIMEOUT 尚无写入路径,
    新增状态转移必须先扩展本映射,未覆盖状态直接 KeyError。
    """
    return _LOBEHUB_STATUS_MAP[status]


def summary_for_session(session: RunSession) -> dict[str, Any]:
    """Build the legacy gateway summary from one retained session."""
    payload: dict[str, Any] = {
        "run_id": session.run_id,
        "trace_id": session.trace_id,
        "status": session.status.value,
        "session_status": to_lobehub_session_status(session.status),
        "mode": session.mode,
        "agent": {"id": session.agent.agent_id, "name": session.agent.name},
        "question": session.question,
        "error": session.error,
    }
    if session.approval_request is not None:
        payload["approval_request"] = session.approval_request
    return payload


__all__ = ["summary_for_session", "to_lobehub_session_status"]
