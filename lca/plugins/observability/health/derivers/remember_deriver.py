"""``RememberDeriver`` — observe the remember phase fold (PR-1 / Task 1.3).

Spec §10.4 status rules mirror ``ReflectDeriver``:

    ok       if ``remember.*.fold.end`` is present
    unknown  if no ``remember.*`` events (phase may be absent)
    degraded / ``failed`` not exercised in v1.
"""

from __future__ import annotations

from lca.contracts.observability.health import RunHealthCondition
from lca.plugins.observability.health.derivers._spine import (
    SpineEvent,
    make_evidence_ref,
    parse_observed_at,
)

REMEMBER_FOLD_EP: str = "phase.remember.fold"


class RememberDeriver:
    """Remember-phase health deriver."""

    def evaluate(self, events: list[SpineEvent]) -> list[RunHealthCondition]:
        """Return one condition describing remember-phase health."""
        remember_events = [e for e in events if e["execution_point"] == REMEMBER_FOLD_EP]
        if not remember_events:
            return [
                RunHealthCondition(
                    type="remember",
                    status="unknown",
                    reason="remember_no_events",
                    evidence_refs=(),
                    observed_at=0.0,
                )
            ]
        evidence = tuple(make_evidence_ref(e) for e in remember_events)
        observed_at = max(parse_observed_at(e["ts"]) for e in remember_events)
        return [
            RunHealthCondition(
                type="remember",
                status="ok",
                reason="remember_fold_closed",
                evidence_refs=evidence,
                observed_at=observed_at,
            )
        ]


__all__ = ["REMEMBER_FOLD_EP", "RememberDeriver"]