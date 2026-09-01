"""Agent-layer spine reflector — PR-3.1.

Emits the canonical ``agent_loop.iteration.start`` / ``.end`` events at
the agent layer iteration boundary (CognitiveAgent.run / .resume and
TeamHandle.run). The ``agent_loop`` iteration span is the parent of
the per-turn ``brain.think`` / ``body.tool.execute`` / ``llm.call``
spans (see ADR-0165.1 § 5.2 SpanTree).

Pattern
-------
The agent layer never receives the spine through its Protocol surface
(AgentUnit / TeamUnit). Profile boot installs the run's EventSpine via
``set_active_spine`` (mirroring ``cognition.py`` and ``runtime.py``)
and every agent entry point calls the tiny ``emit_*`` helpers here to
forward to ``spine.append``. When no spine is wired (default in unit
tests), the helpers are silent no-ops — agent semantics and the
existing test surface are unchanged.

FD-1 / FD-2 containment
-----------------------
- ``_safe_append`` swallows ``EventRecord`` validation errors (e.g.
  malformed payload) so a broken helper never blocks the caller;
  logs at WARNING. All other exceptions propagate as FD-1
  fail-fast, which is the framework's contract.
- The wrappers around CognitiveAgent.run / .resume re-raise inner
  exceptions: a failing runtime still surfaces as a failed step;
  only the envelope of the failure becomes a ``.end`` event with
  ``outcome="failure"``.

Scope
-----
This module imports only the public spine surface
(``EventSpine``, ``SpineContext``, ``EXECUTION_POINTS``, ``Outcome``)
and never the legacy ``journal.{engine,backends,stream,step}``
modules — those are forbidden by the brief.
"""

from __future__ import annotations

import logging
from typing import Any

from lca.infrastructure.observability.spine.event_record import (
    Channel,
    EventRecord,
    Outcome,
)
from lca.infrastructure.observability.spine.event_spine import EventSpine
from lca.infrastructure.observability.spine.manifest import EXECUTION_POINTS

log = logging.getLogger(__name__)


# ── process-local active spine accessor ─────────────────────────────
#
# Mirrors cognition.py / runtime.py so the agent layer, the cognition
# layer, and the runtime layer share the same wiring call. Profile
# boot installs the run's EventSpine here so every agent entry point
# can locate it without changing any constructor signature.

_AGENT_LOOP_ITERATION_START: str = "agent_loop.iteration.start"
_AGENT_LOOP_ITERATION_END: str = "agent_loop.iteration.end"

# Sanity-check at import time: these are close-set names that must
# live in EXECUTION_POINTS. A manifest edit that drops them would
# otherwise silently break the wiring.
if _AGENT_LOOP_ITERATION_START not in EXECUTION_POINTS:
    raise RuntimeError(f"{_AGENT_LOOP_ITERATION_START!r} must remain in EXECUTION_POINTS")
if _AGENT_LOOP_ITERATION_END not in EXECUTION_POINTS:
    raise RuntimeError(f"{_AGENT_LOOP_ITERATION_END!r} must remain in EXECUTION_POINTS")


_active_spine: EventSpine | None = None


def set_active_spine(spine: EventSpine | None) -> None:
    """Install or clear the process-local active spine for agent EPs.

    Called by profile boot at the start of a run. Tests call it
    directly to wire a capturing spine. Passing ``None`` clears.
    """
    global _active_spine
    _active_spine = spine


def get_active_spine() -> EventSpine | None:
    """Return the active spine, or ``None`` if no run is in flight."""
    return _active_spine


# ── core emitter ─────────────────────────────────────────────────────


def _safe_append(
    *,
    execution_point: str,
    channel: Channel,
    payload: dict[str, Any] | None = None,
    outcome: Outcome | None = None,
) -> EventRecord | None:
    """Dispatch to the active spine, returning ``None`` when no spine wired.

    Swallows ``EventRecord`` validation errors (malformed payload) so a
    broken helper never blocks the caller; logs at WARNING. All other
    exceptions propagate as FD-1.
    """
    spine = _active_spine
    if spine is None:
        return None
    try:
        return spine.append(
            execution_point=execution_point,
            channel=channel,
            caller_payload=payload,
            outcome=outcome,
        )
    except ValueError as exc:
        # EventRecord post-init validation failure (e.g. unknown EP).
        log.warning(
            "agent_reflector: drop invalid event ep=%s err=%s",
            execution_point,
            exc,
        )
        return None


# ── agent_loop.iteration.start / agent_loop.iteration.end ────────────
#
# The agent layer wraps each top-level turn (fresh or resumed) with
# one pair of events. ``trace_id`` identifies the AgentState trace
# and ``role`` carries the agent's role for downstream grouping. The
# pair is a strict span boundary: a ``.end`` always follows the
# matching ``.start``; an inner exception emits ``.end`` with
# ``outcome="failure"`` before propagating.


def emit_agent_loop_iteration_start(
    *,
    trace_id: str,
    role: str = "",
    iteration_kind: str = "fresh",
) -> EventRecord | None:
    """Emit ``agent_loop.iteration.start`` at the entry of one agent turn.

    ``iteration_kind`` is ``"fresh"`` for a new run or ``"resume"`` for
    a resumed checkpoint — distinguishes the two flavours in the
    spine without inventing a new execution point.
    """
    return _safe_append(
        execution_point=_AGENT_LOOP_ITERATION_START,
        channel="control",
        payload={
            "trace_id": trace_id,
            "role": role,
            "iteration_kind": iteration_kind,
        },
    )


def emit_agent_loop_iteration_end(
    *,
    trace_id: str,
    role: str = "",
    iteration_kind: str = "fresh",
    outcome: Outcome = "success",
) -> EventRecord | None:
    """Emit ``agent_loop.iteration.end`` at the exit of one agent turn.

    ``outcome`` is ``"success"`` on a normal terminal return;
    ``"failure"`` if the runtime raised; ``"cancelled"`` if
    asyncio.CancelledError propagated.
    """
    return _safe_append(
        execution_point=_AGENT_LOOP_ITERATION_END,
        channel="control",
        payload={
            "trace_id": trace_id,
            "role": role,
            "iteration_kind": iteration_kind,
        },
        outcome=outcome,
    )


__all__ = [
    "emit_agent_loop_iteration_end",
    "emit_agent_loop_iteration_start",
    "get_active_spine",
    "set_active_spine",
]
