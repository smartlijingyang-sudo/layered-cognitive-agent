"""``EvidenceRef`` — typed pointer to a specific spine event (PR-1 / Task 1.1).

Upholds AGENTS.md §3 C13 (information bloodline closure): every cross-boundary
reference MUST be a typed ``Contract`` (frozen Pydantic, ``extra="forbid"``).
Per C13 D1 this is the *definition* point of the reference; D2 (the closed
``SPINE_EXECUTION_POINTS`` set) is enforced by the consumer (deriver +
fold), and D3/D4 are the transform and consumer layers in
``lca/plugins/observability/health/``.

Agents and operators should use ``EvidenceRef`` to jump directly to the
relevant spine event. The ``reason`` text on a ``RunHealthCondition`` is
a stable identifier — NOT a human-readable message — and MUST NOT be
parsed to locate evidence. Use this DTO instead.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class EvidenceRef(BaseModel):
    """Pointer to a specific spine event.

    All five fields are required. ``extra="forbid"`` rejects unknown
    kwargs (AGENTS.md §3 C13 — no surprise fields across a seam);
    ``frozen=True`` blocks post-construction mutation (no aliasing of
    one event's reference to another mid-flight).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    spine_path: str  # absolute; matches RunSession.spine_path
    event_id: str  # spine event_id, e.g. "run_<id>:457"
    execution_point: str  # spine EP, must be in SPINE_EXECUTION_POINTS
    seq: int  # 1-based monotonic, from event_id suffix


__all__ = ["EvidenceRef"]
