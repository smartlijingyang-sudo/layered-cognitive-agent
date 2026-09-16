"""``ActDeriver`` — observe the act phase fold and fanout (PR-1 / Task 1.3).

Spec §10.4 status rules:

    ok       if ``act.fanout`` payload has ``routing.next_hint ==
             "fanout_ntom"``, OR no ``act.fanout`` events are present.
    degraded if ``routing.next_hint == "fanout_1to1"`` — fanout
             collapsed to a single tool (warning, not failure).
    failed   if ``routing.next_hint == "fanout_empty"`` — fanout
             unexpectedly produced no dispatchable tool calls.
    unknown  if no ``act.*`` events at all.

The v1 producer emits ``phase.act.fold``, ``phase.act.fold.end``, and
``phase.act.fold.start``; ``act.fanout`` with routing.next_hint is
forthcoming (PR-3 per spec §15 G-19). The deriver accepts any
``act.*`` EP as proof the phase ran and only branches on
``act.fanout`` routing when the EP is present.
"""

from __future__ import annotations

from lca.contracts.observability.health import RunHealthCondition
from lca.plugins.observability.health.derivers._spine import (
    SpineEvent,
    filter_by_ep,
    make_evidence_ref,
    parse_observed_at,
)

ACT_FANOUT_EP: str = "act.fanout"
ACT_FOLD_END_EP: str = "phase.act.fold.end"
ACT_FOLD_EP: str = "phase.act.fold"
ACT_FOLD_START_EP: str = "phase.act.fold.start"

_ACT_PHASE_EPS: frozenset[str] = frozenset(
    {ACT_FANOUT_EP, ACT_FOLD_END_EP, ACT_FOLD_EP, ACT_FOLD_START_EP}
)


class ActDeriver:
    """Act-phase health deriver."""

    def evaluate(self, events: list[SpineEvent]) -> list[RunHealthCondition]:
        """Return one condition describing act-phase health."""
        fanouts = filter_by_ep(events, ACT_FANOUT_EP)
        if fanouts:
            return _classify_fanout(fanouts)
        phase_events = [
            e for e in events if e["execution_point"] in _ACT_PHASE_EPS
        ]
        if not phase_events:
            return [
                RunHealthCondition(
                    type="act",
                    status="unknown",
                    reason="act_no_events",
                    evidence_refs=(),
                    observed_at=0.0,
                )
            ]
        evidence = tuple(make_evidence_ref(e) for e in phase_events)
        observed_at = max(parse_observed_at(e["ts"]) for e in phase_events)
        return [
            RunHealthCondition(
                type="act",
                status="ok",
                reason="act_fold_closed",
                evidence_refs=evidence,
                observed_at=observed_at,
            )
        ]


def _classify_fanout(fanouts: list[SpineEvent]) -> list[RunHealthCondition]:
    """Map fanout ``next_hint`` values to the closed status alphabet."""
    hints = [
        f["payload"].get("routing", {}).get("next_hint")
        for f in fanouts
    ]
    worst_hint: str | None = None
    for h in hints:
        if h == "fanout_empty":
            worst_hint = "fanout_empty"
            break  # failed wins, stop scanning
        if h == "fanout_1to1" and worst_hint is None:
            worst_hint = "fanout_1to1"

    if worst_hint == "fanout_empty":
        return _emit("failed", "act_fanout_empty", fanouts)
    if worst_hint == "fanout_1to1":
        return _emit("degraded", "act_fanout_1to1", fanouts)
    return _emit("ok", "act_fanout_ntom", fanouts)


def _emit(
    status: str,
    reason: str,
    evidence_events: list[SpineEvent],
) -> list[RunHealthCondition]:
    evidence = tuple(make_evidence_ref(e) for e in evidence_events)
    observed_at = max(parse_observed_at(e["ts"]) for e in evidence_events)
    return [
        RunHealthCondition(
            type="act",
            status=status,  # type: ignore[arg-type]
            reason=reason,
            evidence_refs=evidence,
            observed_at=observed_at,
        )
    ]


__all__ = [
    "ACT_FANOUT_EP",
    "ACT_FOLD_END_EP",
    "ACT_FOLD_EP",
    "ACT_FOLD_START_EP",
    "ActDeriver",
]