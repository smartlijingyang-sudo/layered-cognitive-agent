"""Carrier-facing projections for one retained run session.

This module owns translation from the mutable ``RunSession`` model to the
small, stable payload consumed by legacy gateway query paths.  The registry
retains sessions; it does not know the carrier payload schema.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gateway.runs.session import RunSession


def summary_for_session(session: RunSession) -> dict[str, Any]:
    """Build the legacy gateway summary from one retained session."""
    payload: dict[str, Any] = {
        "run_id": session.run_id,
        "trace_id": session.trace_id,
        "status": session.status.value,
        "session_status": session.status.to_lobehub_session_status(),
        "mode": session.mode,
        "agent": {"id": session.agent.agent_id, "name": session.agent.name},
        "question": session.question,
        "error": session.error,
    }
    if session.approval_request is not None:
        payload["approval_request"] = session.approval_request
    return payload


__all__ = ["summary_for_session"]
