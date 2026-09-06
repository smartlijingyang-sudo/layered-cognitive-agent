"""Runtime spine fact production (ADR-0194 P2-10).

Single production seam for runtime envelope EPs via ``publish_ep_bound``.
All helpers no-op when no Session is bound (tests / offline).
"""

from __future__ import annotations

from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.loop.fact_gateway import AppendReceipt
from lca.loop.fact_gateway import publish_ep_bound

_active_run_id: str = ""


def set_active_run_id(run_id: str | None) -> None:
    """Install the active run_id for runtime EP payloads."""
    global _active_run_id
    _active_run_id = str(run_id or "")


def _coerce_run_id(explicit: str | None) -> str:
    return str(explicit or "") or _active_run_id


def emit_runtime_reducer_apply_start(
    *,
    method: str,
    run_id: str | None = None,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "reducer",
) -> AppendReceipt | None:
    """Append one ``runtime.reducer.apply`` start-side marker."""
    return publish_ep_bound(
        "runtime.reducer.apply",
        {
            "method": method,
            "phase": "start",
            "run_id": _coerce_run_id(run_id),
        },
        state=state,
        session=session,
        actor=actor,
    )


def emit_runtime_reducer_apply_end(
    *,
    method: str,
    outcome: str,
    run_id: str | None = None,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "reducer",
) -> AppendReceipt | None:
    """Append one ``runtime.reducer.apply`` end-side marker."""
    return publish_ep_bound(
        "runtime.reducer.apply",
        {
            "method": method,
            "phase": "end",
            "outcome": outcome,
            "run_id": _coerce_run_id(run_id),
        },
        state=state,
        session=session,
        actor=actor,
    )


def emit_runtime_checkpoint_create(
    *,
    plan_ref: str,
    state_ref: str,
    node_id: str,
    outcome: str = "success",
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "runtime",
) -> AppendReceipt | None:
    """Append one ``runtime.checkpoint.create`` spine fact."""
    return publish_ep_bound(
        "runtime.checkpoint.create",
        {
            "plan_ref": plan_ref,
            "state_ref": state_ref,
            "node_id": node_id,
            "outcome": outcome,
        },
        state=state,
        session=session,
        actor=actor,
    )


def emit_runtime_resume_start(
    *,
    plan_ref: str,
    state_ref: str,
    node_id: str,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "runtime",
) -> AppendReceipt | None:
    """Append one ``runtime.resume.start`` spine fact."""
    return publish_ep_bound(
        "runtime.resume.start",
        {
            "plan_ref": plan_ref,
            "state_ref": state_ref,
            "node_id": node_id,
        },
        state=state,
        session=session,
        actor=actor,
    )


def emit_runtime_resume_end(
    *,
    plan_ref: str,
    state_ref: str,
    node_id: str,
    outcome: str,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "runtime",
) -> AppendReceipt | None:
    """Append one ``runtime.resume.end`` spine fact."""
    return publish_ep_bound(
        "runtime.resume.end",
        {
            "plan_ref": plan_ref,
            "state_ref": state_ref,
            "node_id": node_id,
            "outcome": outcome,
        },
        state=state,
        session=session,
        actor=actor,
    )


def emit_runtime_event_publisher_publish(
    *,
    event_type: str,
    trace_id: str,
    outcome: str = "success",
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "runtime",
) -> AppendReceipt | None:
    """Append one ``runtime.event_publisher.publish`` spine fact."""
    return publish_ep_bound(
        "runtime.event_publisher.publish",
        {
            "event_type": event_type,
            "trace_id": trace_id,
            "outcome": outcome,
        },
        state=state,
        session=session,
        actor=actor,
    )


def emit_runtime_observed(
    *,
    observed_at: str,
    detail: str,
    run_id: str | None = None,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "runtime",
) -> AppendReceipt | None:
    """Append one ``runtime.observed`` diagnostic marker."""
    return publish_ep_bound(
        "runtime.observed",
        {
            "observed_at": observed_at,
            "detail": detail,
            "run_id": run_id or "",
        },
        state=state,
        session=session,
        actor=actor,
    )


def emit_exception_finally(
    *,
    boundary: str,
    trace_id: str | None = None,
    outcome: str = "failure",
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "runtime",
) -> AppendReceipt | None:
    """Append one ``exception.finally`` spine fact (exception path only)."""
    return publish_ep_bound(
        "exception.finally",
        {
            "boundary": boundary,
            "trace_id": trace_id or "",
            "outcome": outcome,
        },
        state=state,
        session=session,
        actor=actor,
    )


def emit_lifecycle_finally(
    *,
    boundary: str,
    trace_id: str | None = None,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "runtime",
) -> AppendReceipt | None:
    """Append one ``lifecycle.finally`` spine fact (success path)."""
    return publish_ep_bound(
        "lifecycle.finally",
        {
            "boundary": boundary,
            "trace_id": trace_id or "",
            "outcome": "success",
        },
        state=state,
        session=session,
        actor=actor,
    )


__all__ = [
    "emit_exception_finally",
    "emit_lifecycle_finally",
    "emit_runtime_checkpoint_create",
    "emit_runtime_event_publisher_publish",
    "emit_runtime_observed",
    "emit_runtime_reducer_apply_end",
    "emit_runtime_reducer_apply_start",
    "emit_runtime_resume_end",
    "emit_runtime_resume_start",
    "set_active_run_id",
]
