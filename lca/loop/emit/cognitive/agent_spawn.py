"""Agent loop + agent lifecycle spine EP production (ADR-0194 P2-14 / P5 wrap-up)."""

from __future__ import annotations

from lca.contracts.models.core.state import AgentState
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


def emit_agent_spawn(
    *,
    trace_id: str,
    role: str,
    agent_id: str,
    state: AgentState | None = None,
    session: object | None = None,
) -> SpineEmitRef | None:
    """Emit when a new agent is spawned into the run."""
    return publish_spine_ep(
        "agent.spawn",
        {"trace_id": trace_id, "role": role, "agent_id": agent_id},
        channel="control",
        actor=_AGENT_SPAWN_ACTOR,
        state=state,
        session=session,
    )


def emit_agent_iteration(
    *,
    trace_id: str,
    role: str,
    agent_id: str,
    iteration: int,
    state: AgentState | None = None,
    session: object | None = None,
) -> SpineEmitRef | None:
    """Emit at the start of each agent-level iteration."""
    return publish_spine_ep(
        "agent.iteration",
        {
            "trace_id": trace_id,
            "role": role,
            "agent_id": agent_id,
            "iteration": iteration,
        },
        channel="control",
        actor=_AGENT_SPAWN_ACTOR,
        state=state,
        session=session,
    )


def emit_agent_final(
    *,
    trace_id: str,
    role: str,
    agent_id: str,
    outcome: str = "success",
    state: AgentState | None = None,
    session: object | None = None,
) -> SpineEmitRef | None:
    """Emit at agent final (terminal)."""
    return publish_spine_ep(
        "agent.final",
        {
            "trace_id": trace_id,
            "role": role,
            "agent_id": agent_id,
            "outcome": outcome,
        },
        channel="control",
        actor=_AGENT_SPAWN_ACTOR,
        state=state,
        session=session,
    )


__all__ = [
    "emit_agent_final",
    "emit_agent_iteration",
    "emit_agent_loop_iteration_end",
    "emit_agent_loop_iteration_start",
    "emit_agent_spawn",
]
