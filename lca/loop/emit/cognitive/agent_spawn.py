"""Agent loop + agent lifecycle spine EP production (ADR-0194 P2-14 / P5 wrap-up)."""

from __future__ import annotations

from lca.contracts.models.core.state.state import AgentState
from lca.loop.emit.spine.ep import SpineEmitRef, publish_spine_ep

_AGENT_SPAWN_ACTOR = "agent_spawn"


def emit_agent_loop_iteration_start(
    *,
    trace_id: str,
    role: str = "",
    iteration_kind: str = "fresh",
    state: AgentState | None = None,
    session: object | None = None,
) -> SpineEmitRef | None:
    """Emit ``agent_loop.iteration.start`` at the entry of one agent turn."""
    return publish_spine_ep(
        "agent_loop.iteration.start",
        {
            "trace_id": trace_id,
            "role": role,
            "iteration_kind": iteration_kind,
        },
        channel="control",
        actor=_AGENT_SPAWN_ACTOR,
        state=state,
        session=session,
    )


def emit_agent_loop_iteration_end(
    *,
    trace_id: str,
    role: str = "",
    iteration_kind: str = "fresh",
    outcome: str = "success",
    state: AgentState | None = None,
    session: object | None = None,
) -> SpineEmitRef | None:
    """Emit ``agent_loop.iteration.end`` at the exit of one agent turn."""
    return publish_spine_ep(
        "agent_loop.iteration.end",
        {
            "trace_id": trace_id,
            "role": role,
            "iteration_kind": iteration_kind,
            "outcome": outcome,
        },
        channel="control",
        actor=_AGENT_SPAWN_ACTOR,
        state=state,
        session=session,
    )


__all__ = [
    "emit_agent_loop_iteration_end",
    "emit_agent_loop_iteration_start",
]
