"""Orphan event helpers — mark live ``EventRecord``s as ``phase="orphan"``.

PR-6 spine-orphan-events (ADR-0165.1 §19, design §4.3): an event
emitted when no active step is open cannot belong to the step tree
and must not flow through ``StepTreeDeriver``. It still reaches the
append-only ``events.jsonl`` via the sink so diagnosis remains
possible, but the ``phase="orphan"`` + ``reason`` tags tell consumers
(e.g. ``lca-ops journal trace --include-orphan``) why it stands alone.

``reason`` is a close enum — adding a value requires an ADR.
"""

from __future__ import annotations

import dataclasses

from lca.infrastructure.observability.spine.event_record import EventRecord

# Close enum (ADR-0165.1 §19, design §4.3). Extend via ADR only.
CANCEL_PRE_BOOT: str = "cancel_pre_boot"
STOP_BEFORE_STEP: str = "stop_before_step"
FAIL_BEFORE_STEP: str = "fail_before_step"
PENDING_TOOL_CALL: str = "pending_tool_call"
PANIC: str = "panic"

ORPHAN_REASONS: frozenset[str] = frozenset(
    {
        CANCEL_PRE_BOOT,
        STOP_BEFORE_STEP,
        FAIL_BEFORE_STEP,
        PENDING_TOOL_CALL,
        PANIC,
    }
)


def mark_orphan(rec: EventRecord, reason: str) -> EventRecord:
    """Return a copy of ``rec`` tagged ``phase="orphan"`` with ``reason``.

    ``EventRecord`` is frozen; ``dataclasses.replace`` produces a new
    instance carrying the override fields. ``EventRecord.__post_init__``
    enforces the orphan-needs-reason invariant, so passing an empty
    or unknown ``reason`` raises ``ValueError`` and the live record is
    never mutated.

    Pass any reason from ``ORPHAN_REASONS``; new reasons require an ADR
    and an update to ``ORPHAN_REASONS``.
    """
    if rec.phase == "orphan":
        raise ValueError(
            f"EventRecord already phase='orphan' reason={rec.reason!r}; "
            "mark_orphan is idempotent w.r.t. live records"
        )
    return dataclasses.replace(rec, phase="orphan", reason=reason)


__all__ = [
    "CANCEL_PRE_BOOT",
    "FAIL_BEFORE_STEP",
    "ORPHAN_REASONS",
    "PANIC",
    "PENDING_TOOL_CALL",
    "STOP_BEFORE_STEP",
    "mark_orphan",
]
