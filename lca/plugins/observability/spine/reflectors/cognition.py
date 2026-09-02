"""Cognition spine reflector — PR-3.2.

Emits canonical ``EXECUTION_POINTS`` events from the cognition layer
entry points (Brain.think, Reasoner.generate_thoughts, Critic.critique,
Synthesizer.synthesize, SkillRouter.route, MemorySystem.perceive/commit,
plus the cooperative ``memory.read`` / ``memory.write`` channels).

Pattern
-------
The cognition layer calls tiny ``emit_*`` helpers here before and after
each public method body. Helpers read the process-local active spine
installed by ``set_active_spine`` (called by the bootstrap/profile) and
call ``spine.append(...)``. When no spine is wired (default in
unit tests), the helpers are silent no-ops — cognition semantics and
existing test surface are unchanged.

FD-1 / FD-2 containment
-----------------------
- ``emit_*`` wraps ``spine.append`` in ``try/except``: a broken sink
  propagates from ``spine.append`` (FD-1 fail-fast), which is the
  framework's contract; the helper itself never adds another failure
  surface above it. Emission errors that slip past FD-1 (e.g. an
  ``EventRecord`` validation issue raised by a malformed payload) are
  contained by the helper so cognition business logic is not blocked.
- The wrappers around inner cognition methods also re-raise the
  inner exception: a failing Reasoner / Critic still surfaces as a
  failed step; only the *envelope* of the failure becomes a
  ``.end`` event with ``outcome="failure"``.

The module imports only the public spine surface
(``EventSpine``, ``SpineContext``, ``EXECUTION_POINTS``) and the
``Outcome`` type. It does NOT import the legacy journal facade or
any ``journal.{engine,backends,stream,step}`` module — those are
forbidden by the brief.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from lca.infrastructure.observability.spine.event_record import (
    Channel,
    EventRecord,
    Outcome,
)
from lca.infrastructure.observability.spine.event_spine import EventSpine

log = logging.getLogger(__name__)


# ── process-local active spine accessor ─────────────────────────────
#
# The cognition layer never receives the spine through its Protocol
# surface (Brain / Reasoner / Critic / Synthesizer / SkillRouter /
# MemorySystem). Profile boot installs the run's EventSpine here so
# every cognition call can locate it without changing any constructor
# signature. Tests use the same setter to inject a capturing sink.

_active_spine: EventSpine | None = None


def set_active_spine(spine: EventSpine | None) -> None:
    """Install or clear the process-local active spine.

    Called by profile boot (``kernel_serve`` / ``boot_resolved_profile``)
    at the start of a run. Tests call it directly to wire a capturing
    spine. Passing ``None`` clears the binding.
    """
    global _active_spine
    _active_spine = spine


def get_active_spine() -> EventSpine | None:
    """Return the active spine, or ``None`` if no run is in flight."""
    return _active_spine


# ── core emitter ──────────────────────────────────────────────────────


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
            "cognition_reflector: drop invalid event ep=%s err=%s",
            execution_point,
            exc,
        )
        return None


# ── brain.perceive (executed by PerceiveHub; emitted in the brain layer
# when Brain composition routes through Perception-aware hooks).
# ─────────────────────────────────────────────────────────────────────


def emit_brain_perceive_start(*, state_id: str) -> EventRecord | None:
    return _safe_append(
        execution_point="brain.perceive.start",
        channel="fact",
        payload={"state_id": state_id},
    )


def emit_brain_perceive_end(*, state_id: str, outcome: Outcome = "success") -> EventRecord | None:
    return _safe_append(
        execution_point="brain.perceive.end",
        channel="fact",
        payload={"state_id": state_id},
        outcome=outcome,
    )


# ── brain.think ───────────────────────────────────────────────────────


def emit_brain_think_start(*, state_id: str) -> EventRecord | None:
    return _safe_append(
        execution_point="brain.think.start",
        channel="fact",
        payload={"state_id": state_id},
    )


def emit_brain_think_end(*, state_id: str, outcome: Outcome = "success") -> EventRecord | None:
    return _safe_append(
        execution_point="brain.think.end",
        channel="fact",
        payload={"state_id": state_id},
        outcome=outcome,
    )


# ── brain.gate ────────────────────────────────────────────────────────


def emit_brain_gate_start(*, state_id: str) -> EventRecord | None:
    return _safe_append(
        execution_point="brain.gate.start",
        channel="control",
        payload={"state_id": state_id},
    )


def emit_brain_gate_end(*, state_id: str, outcome: Outcome = "success") -> EventRecord | None:
    return _safe_append(
        execution_point="brain.gate.end",
        channel="control",
        payload={"state_id": state_id},
        outcome=outcome,
    )


# ── critic.eval ───────────────────────────────────────────────────────


def emit_critic_eval_start(*, state_id: str) -> EventRecord | None:
    return _safe_append(
        execution_point="critic.eval.start",
        channel="fact",
        payload={"state_id": state_id},
    )


def emit_critic_eval_end(*, state_id: str, outcome: Outcome = "success") -> EventRecord | None:
    return _safe_append(
        execution_point="critic.eval.end",
        channel="fact",
        payload={"state_id": state_id},
        outcome=outcome,
    )


# ── reasoner.reason ──────────────────────────────────────────────────


def emit_reasoner_reason_start(*, state_id: str) -> EventRecord | None:
    return _safe_append(
        execution_point="reasoner.reason.start",
        channel="fact",
        payload={"state_id": state_id},
    )


def emit_reasoner_reason_end(*, state_id: str, outcome: Outcome = "success") -> EventRecord | None:
    return _safe_append(
        execution_point="reasoner.reason.end",
        channel="fact",
        payload={"state_id": state_id},
        outcome=outcome,
    )


# ── prompt_assembler.assemble ───────────────────────────────────────


def emit_prompt_assembler_start(
    *,
    state_id: str,
    template_id: str,
    sections: Sequence[str] | None = None,
    decision_path: str | None = None,
    activated_skills: Sequence[str] | None = None,
    tools_count: int | None = None,
    available_skills_count: int | None = None,
) -> EventRecord | None:
    payload: dict[str, Any] = {"state_id": state_id, "template_id": template_id}
    if sections is not None:
        payload["sections"] = list(sections)
    if decision_path is not None:
        payload["decision_path"] = decision_path
    if activated_skills is not None:
        payload["activated_skills"] = list(activated_skills)
    if tools_count is not None:
        payload["tools_count"] = tools_count
    if available_skills_count is not None:
        payload["available_skills_count"] = available_skills_count
    return _safe_append(
        execution_point="prompt_assembler.assemble.start",
        channel="fact",
        payload=payload,
    )


def emit_prompt_assembler_end(
    *,
    state_id: str,
    template_id: str,
    section_count: int,
    section_outputs: Sequence[Mapping[str, Any]] | None = None,
    total_chars: int | None = None,
    outcome: Outcome = "success",
) -> EventRecord | None:
    payload: dict[str, Any] = {
        "state_id": state_id,
        "template_id": template_id,
        "section_count": section_count,
    }
    if section_outputs is not None:
        payload["section_outputs"] = [
            {k: v for k, v in dict(item).items() if v is not None} for item in section_outputs
        ]
    if total_chars is not None:
        payload["total_chars"] = total_chars
    return _safe_append(
        execution_point="prompt_assembler.assemble.end",
        channel="fact",
        payload=payload,
        outcome=outcome,
    )


# ── synthesizer.merge ────────────────────────────────────────────────


def emit_synthesizer_merge(
    *, state_id: str, candidate_count: int, outcome: Outcome = "success"
) -> EventRecord | None:
    return _safe_append(
        execution_point="synthesizer.merge",
        channel="fact",
        payload={"state_id": state_id, "candidate_count": candidate_count},
        outcome=outcome,
    )


# ── skill_router.route ───────────────────────────────────────────────


def emit_skill_router_route(
    *,
    state_id: str,
    template: str,
    decision_path: str | None = None,
    outcome: Outcome = "success",
) -> EventRecord | None:
    payload: dict[str, Any] = {"state_id": state_id, "template": template}
    if decision_path is not None:
        payload["decision_path"] = decision_path
    return _safe_append(
        execution_point="skill_router.route",
        channel="control",
        payload=payload,
        outcome=outcome,
    )


# ── memory.read / memory.write ───────────────────────────────────────


def emit_memory_read(*, state_id: str, outcome: Outcome = "success") -> EventRecord | None:
    return _safe_append(
        execution_point="memory.read",
        channel="fact",
        payload={"state_id": state_id},
        outcome=outcome,
    )


def emit_memory_write(
    *,
    state_id: str,
    layer: str,
    record_id: str | None = None,
    outcome: Outcome = "success",
) -> EventRecord | None:
    payload: dict[str, Any] = {"state_id": state_id, "layer": layer}
    if record_id is not None:
        payload["record_id"] = record_id
    return _safe_append(
        execution_point="memory.write",
        channel="fact",
        payload=payload,
        outcome=outcome,
    )


# ── envelope helpers (used by the cognition layer wrappers) ──────────


__all__ = [
    "emit_brain_gate_end",
    "emit_brain_gate_start",
    "emit_brain_perceive_end",
    "emit_brain_perceive_start",
    "emit_brain_think_end",
    "emit_brain_think_start",
    "emit_critic_eval_end",
    "emit_critic_eval_start",
    "emit_memory_read",
    "emit_memory_write",
    "emit_prompt_assembler_end",
    "emit_prompt_assembler_start",
    "emit_reasoner_reason_end",
    "emit_reasoner_reason_start",
    "emit_skill_router_route",
    "emit_synthesizer_merge",
    "get_active_spine",
    "set_active_spine",
]
