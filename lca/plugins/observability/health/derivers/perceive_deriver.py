"""``PerceiveDeriver`` — observe the perceive phase fold (PR-1 / Task 1.3).

Spec §10.4 status rules:

    ok       if ``phase.perceive.fold`` present
    unknown  if no ``perceive.*`` events

The brief notes that ``degraded`` / ``failed`` paths are not exercised in
v1 — the current producer does not emit ``phase.perceive.fold.start`` /
``.end`` pairs nor an error-flagged perceive fold, so the deriver
collapses both reserved branches to ``unknown`` (no perception observed)
and ``ok`` (perception closed) respectively. Adding a degraded/failed
distinction is a pure addition when the producer grows the EPs.
"""

from __future__ import annotations

from lca.contracts.observability.health import (
    RunHealthCondition,
)
from lca.plugins.observability.health.derivers._spine import (
    SpineEvent,
    filter_by_ep,
    make_evidence_ref,
)

#: The EP that signals a closed perceive fold. Spec §10.4 calls it
#: ``phase.perceive.fold.end``; the v1 producer emits the single EP
#: ``phase.perceive.fold`` and we treat it as the close signal.
PERCEIVE_FOLD_EP: str = "phase.perceive.fold"


class PerceiveDeriver:
    """Perceive-phase health deriver.

    Consumes ``perceive.*`` EPs from the spine and emits exactly one
    ``RunHealthCondition`` per evaluation. Empty events -> ``unknown``;
    any perceive fold present -> ``ok``. The deriver never returns an
    empty list (the fold expects at least one condition per registered
    type so the report has a stable shape per spec §10.5 property 2).
    """

    def evaluate(self, events: list[SpineEvent]) -> list[RunHealthCondition]:
        """Return one condition describing perceive phase health.

        Status alphabet: ``ok`` (perceive fold present) or ``unknown``
        (no perceive events). Both reserved branches
        (``degraded`` / ``failed``) collapse to ``unknown`` / ``ok``
        respectively in v1; see module docstring.
        """
        perceive_events = filter_by_ep(events, PERCEIVE_FOLD_EP)
        if perceive_events:
            evidence = tuple(make_evidence_ref(e) for e in perceive_events)
            observed_at = max(e["ts"] for e in perceive_events)  # monotonic per type
            return [
                RunHealthCondition(
                    type="perceive",
                    status="ok",
                    reason="perceive_fold_closed",
                    evidence_refs=evidence,
                    observed_at=_to_epoch(observed_at),
                )
            ]
        return [
            RunHealthCondition(
                type="perceive",
                status="unknown",
                reason="perceive_no_events",
                evidence_refs=(),
                observed_at=0.0,
            )
        ]


def _to_epoch(ts: str) -> float:
    from lca.plugins.observability.health.derivers._spine import parse_observed_at

    return parse_observed_at(ts)


__all__ = ["PERCEIVE_FOLD_EP", "PerceiveDeriver"]
