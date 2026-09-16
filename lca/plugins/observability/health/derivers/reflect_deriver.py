"""``ReflectDeriver`` — observe the reflect phase fold (PR-1 / Task 1.3).

Spec §10.4 status rules:

    ok       if ``reflect.*.fold.end`` is present
    unknown  if no ``reflect.*`` events (reflect may be absent in
             some profiles — v1 leaves the phase optional)
    degraded / ``failed`` not exercised in v1; the v1 producer does
             not emit ``reflect.*.fold.start`` / ``.end`` pairs nor
             an error-outcome variant, so both reserved branches
             collapse to ``unknown`` / ``ok`` respectively.

Mirrors ``RememberDeriver`` because the two phases share the same
shape: an optional phase whose presence signals that the loop closed.
The 4-case schema is kept for uniformity across the eight derivers.
"""

from __future__ import annotations

from lca.contracts.observability.health import RunHealthCondition
from lca.plugins.observability.health.derivers._spine import (
    SpineEvent,
    make_evidence_ref,
    parse_observed_at,
)

REFLECT_FOLD_EP: str = "phase.reflect.fold"


class ReflectDeriver:
    """Reflect-phase health deriver."""

    def evaluate(self, events: list[SpineEvent]) -> list[RunHealthCondition]:
        """Return one condition describing reflect-phase health."""
        reflect_events = [e for e in events if e["execution_point"] == REFLECT_FOLD_EP]
        if not reflect_events:
            return [
                RunHealthCondition(
                    type="reflect",
                    status="unknown",
                    reason="reflect_no_events",
                    evidence_refs=(),
                    observed_at=0.0,
                )
            ]
        evidence = tuple(make_evidence_ref(e) for e in reflect_events)
        observed_at = max(parse_observed_at(e["ts"]) for e in reflect_events)
        return [
            RunHealthCondition(
                type="reflect",
                status="ok",
                reason="reflect_fold_closed",
                evidence_refs=evidence,
                observed_at=observed_at,
            )
        ]


__all__ = ["REFLECT_FOLD_EP", "ReflectDeriver"]