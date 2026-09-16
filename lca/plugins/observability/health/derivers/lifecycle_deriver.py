"""``LifecycleDeriver`` — observe the kernel run-stop terminal outcome (PR-1 / Task 1.3).

Spec §10.4 status rules:

    ok       if ``kernel.run.stop`` payload has ``outcome == "success"``
    failed   if outcome is anything other than "success" — the brief
             enumerates {failed, error, failure, timeout, ...} but the
             implementation treats all non-success values uniformly
             to avoid a closed-set drift trap (any future outcome
             string added by the producer is implicitly failed).
    unknown  if no ``kernel.run.stop`` event
    degraded reserved for ``outcome == "degraded"`` (not emitted in v1)

Only ``kernel.run.stop`` drives this deriver. ``lifecycle.finally`` reports
teardown-boundary success (``emit_lifecycle_finally`` hardcodes
``outcome="success"``), so it carries no run outcome and the journal fold does
not read it either.
"""

from __future__ import annotations

from lca.contracts.observability.health import RunHealthCondition
from lca.plugins.observability.health.derivers._spine import (
    SpineEvent,
    filter_by_ep,
    make_evidence_ref,
    parse_observed_at,
)

KERNEL_RUN_STOP_EP: str = "kernel.run.stop"


class LifecycleDeriver:
    """Kernel lifecycle health deriver."""

    def evaluate(self, events: list[SpineEvent]) -> list[RunHealthCondition]:
        """Return one condition describing the terminal lifecycle outcome.

        When multiple ``kernel.run.stop`` events exist (e.g. recovery
        loop), the LAST event wins — the health report reflects the
        final terminal state, not the intermediate attempts.
        """
        stops = filter_by_ep(events, KERNEL_RUN_STOP_EP)
        if not stops:
            return [
                RunHealthCondition(
                    type="lifecycle",
                    status="unknown",
                    reason="lifecycle_no_events",
                    evidence_refs=(),
                    observed_at=0.0,
                )
            ]
        last = stops[-1]
        outcome = last["payload"].get("outcome")
        if outcome == "success":
            return [_emit("ok", "lifecycle_outcome_success", [last])]
        return [_emit("failed", "lifecycle_outcome_failed", [last])]


def _emit(
    status: str,
    reason: str,
    evidence_events: list[SpineEvent],
) -> RunHealthCondition:
    evidence = tuple(make_evidence_ref(e) for e in evidence_events)
    observed_at = max(parse_observed_at(e["ts"]) for e in evidence_events)
    return RunHealthCondition(
        type="lifecycle",
        status=status,  # type: ignore[arg-type]
        reason=reason,
        evidence_refs=evidence,
        observed_at=observed_at,
    )


__all__ = ["KERNEL_RUN_STOP_EP", "LifecycleDeriver"]
