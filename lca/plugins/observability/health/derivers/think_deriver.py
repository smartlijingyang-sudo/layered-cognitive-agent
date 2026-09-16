"""``ThinkDeriver`` — observe the think phase fold (PR-1 / Task 1.3).

Spec §10.4 status rules:

    ok       if ``think.main.start`` is followed by a
             ``think.decision.repair`` with non-empty routing
    degraded if a ``think.decision.repair`` is present but its routing
             payload is empty (no next-action emitted)
    failed   if ``think.decision.repair`` outputs a routing whose
             ``action_type == "error"`` (or status indicates an error)
    unknown  if no ``think.*`` events

The v1 producer emits ``phase.think.fold`` and ``think.gate.start`` —
the spec's ``think.main.start`` / ``think.decision.repair`` pair is
forthcoming. The deriver accepts any of the documented think EPs as
proof that the think phase ran; the ``degraded`` / ``failed`` branches
are reserved for future ``think.decision.repair`` events. When both
fold evidence and a repair event coexist, the worst status wins
(``failed`` > ``degraded`` > ``ok``).
"""

from __future__ import annotations

from lca.contracts.observability.health import RunHealthCondition
from lca.plugins.observability.health.derivers._spine import (
    SpineEvent,
    make_evidence_ref,
    parse_observed_at,
)

#: EPs that prove the think phase ran. Spec calls out
#: ``think.main.start`` and ``think.decision.repair``; the v1 producer
#: emits ``phase.think.fold`` and ``think.gate.start`` so we accept any
#: of these.
THINK_FOLD_EP: str = "phase.think.fold"
THINK_GATE_START_EP: str = "think.gate.start"
THINK_DECISION_REPAIR_EP: str = "think.decision.repair"

_THINK_PROXY_EPS: frozenset[str] = frozenset(
    {THINK_FOLD_EP, THINK_GATE_START_EP, THINK_DECISION_REPAIR_EP}
)


class ThinkDeriver:
    """Think-phase health deriver."""

    def evaluate(self, events: list[SpineEvent]) -> list[RunHealthCondition]:
        """Return one condition describing think-phase health."""
        think_events = [e for e in events if e["execution_point"] in _THINK_PROXY_EPS]
        repair_events = [e for e in events if e["execution_point"] == THINK_DECISION_REPAIR_EP]
        if not think_events:
            return [
                RunHealthCondition(
                    type="think",
                    status="unknown",
                    reason="think_no_events",
                    evidence_refs=(),
                    observed_at=0.0,
                )
            ]

        # Decision-repair events take priority over fold/gate presence.
        failed_repairs = [
            e for e in repair_events if _routing_is_error(e["payload"].get("routing", {}))
        ]
        empty_repairs = [
            e for e in repair_events if _routing_is_empty(e["payload"].get("routing", {}))
        ]
        if failed_repairs:
            return _emit("failed", "think_decision_error", failed_repairs)
        if empty_repairs:
            return _emit("degraded", "think_routing_empty", empty_repairs)
        return _emit("ok", "think_fold_closed", think_events)


def _routing_is_empty(routing: dict) -> bool:  # type: ignore[type-arg]
    """Routing is empty when no keys, or only empty-valued keys."""
    if not routing:
        return True
    return all(v in (None, "", [], {}) for v in routing.values())


def _routing_is_error(routing: dict) -> bool:  # type: ignore[type-arg]
    """Routing signals error when ``action_type == "error"`` or similar."""
    if not routing:
        return False
    action = routing.get("action_type")
    if isinstance(action, str) and action.lower() in {"error", "fail", "failed"}:
        return True
    # some producers emit {"status": "error"} instead
    status = routing.get("status")
    return bool(isinstance(status, str) and status.lower() in {"error", "failed", "failure"})


def _emit(
    status: str,
    reason: str,
    evidence_events: list[SpineEvent],
) -> list[RunHealthCondition]:
    evidence = tuple(make_evidence_ref(e) for e in evidence_events)
    observed_at = max(parse_observed_at(e["ts"]) for e in evidence_events)
    return [
        RunHealthCondition(
            type="think",
            status=status,  # type: ignore[arg-type]
            reason=reason,
            evidence_refs=evidence,
            observed_at=observed_at,
        )
    ]


__all__ = [
    "THINK_DECISION_REPAIR_EP",
    "THINK_FOLD_EP",
    "THINK_GATE_START_EP",
    "ThinkDeriver",
]
