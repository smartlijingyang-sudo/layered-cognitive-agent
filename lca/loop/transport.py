"""Transport + kernel.run spine EP production (ADR-0194 P2-15 / P5 wrap-up).

Carrier-plane route and kernel run lifecycle facts via FactGateway.
"""

from __future__ import annotations

from typing import Any

from lca.contracts.models.core.state import AgentState
from lca.loop.emit.spine.ep import SpineEmitRef, publish_spine_ep

_TRANSPORT_ACTOR = "transport"


def emit_transport_route_enter(
    *,
    path: str,
    method: str,
    run_id: str | None = None,
    carrier_seq: int | None = None,
    state: AgentState | None = None,
    session: object | None = None,
) -> SpineEmitRef | None:
    """Carrier-plane route enter (ADR-0166 S4: optional ``carrier_seq``)."""
    payload: dict[str, Any] = {"path": path, "method": method, "run_id": run_id or ""}
    if carrier_seq is not None:
        payload["carrier_seq"] = carrier_seq
    return publish_spine_ep(
        "transport.route.enter",
        payload,
        channel="control",
        actor=_TRANSPORT_ACTOR,
        state=state,
        session=session,
    )


def emit_transport_route_exit(
    *,
    path: str,
    method: str,
    outcome: str = "success",
    run_id: str | None = None,
    carrier_seq: int | None = None,
    state: AgentState | None = None,
    session: object | None = None,
) -> SpineEmitRef | None:
    """Carrier-plane route exit (ADR-0166 S4)."""
    payload: dict[str, Any] = {
        "path": path,
        "method": method,
        "run_id": run_id or "",
        "outcome": outcome,
    }
    if carrier_seq is not None:
        payload["carrier_seq"] = carrier_seq
    return publish_spine_ep(
        "transport.route.exit",
        payload,
        channel="control",
        actor=_TRANSPORT_ACTOR,
        state=state,
        session=session,
    )


def emit_transport_sse_publish(
    *,
    path: str,
    run_id: str | None = None,
    state: AgentState | None = None,
    session: object | None = None,
) -> SpineEmitRef | None:
    return publish_spine_ep(
        "transport.sse.publish",
        {"path": path, "run_id": run_id or ""},
        channel="control",
        actor=_TRANSPORT_ACTOR,
        state=state,
        session=session,
    )


def emit_kernel_run_start(
    *,
    run_id: str,
    trace_id: str = "",
    state: AgentState | None = None,
    session: object | None = None,
) -> SpineEmitRef | None:
    return publish_spine_ep(
        "kernel.run.start",
        {"run_id": run_id, "trace_id": trace_id},
        channel="control",
        actor=_TRANSPORT_ACTOR,
        state=state,
        session=session,
    )


def emit_kernel_run_stop(
    *,
    run_id: str,
    outcome: str = "success",
    trace_id: str = "",
    state: AgentState | None = None,
    session: object | None = None,
) -> SpineEmitRef | None:
    return publish_spine_ep(
        "kernel.run.stop",
        {"run_id": run_id, "trace_id": trace_id, "outcome": outcome},
        channel="control",
        actor=_TRANSPORT_ACTOR,
        state=state,
        session=session,
    )


def emit_kernel_run_cancelled(
    *,
    run_id: str,
    trace_id: str = "",
    state: AgentState | None = None,
    session: object | None = None,
) -> SpineEmitRef | None:
    return publish_spine_ep(
        "kernel.run.cancelled",
        {"run_id": run_id, "trace_id": trace_id, "outcome": "cancelled"},
        channel="control",
        actor=_TRANSPORT_ACTOR,
        state=state,
        session=session,
    )


__all__ = [
    "emit_kernel_run_cancelled",
    "emit_kernel_run_start",
    "emit_kernel_run_stop",
    "emit_transport_route_enter",
    "emit_transport_route_exit",
    "emit_transport_sse_publish",
]
