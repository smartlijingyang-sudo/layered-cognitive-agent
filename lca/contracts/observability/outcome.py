"""Canonical ``Outcome`` Literal for spine events (ADR-0165 / ADR-0165.1).

Single source of truth for the close-set of event outcomes used by
``EventRecord`` and every consumer (projections, journal store, run
ledger, diag emitters). Replaces the inline Literal duplicated in
``lca.infrastructure.observability.spine.event_record`` and the
8-element ``set`` literal duplicated in ``coordinator.emit_phase``.

Adding a new outcome requires an ADR (close-set semantics).
"""

from __future__ import annotations

from typing import Literal

Outcome = Literal[
    "success",
    "failure",
    "timeout",
    "cancelled",
    "rejected",
    "retrying",
    "partial",
    "exhausted",
    "void",
]

__all__ = ["Outcome"]
