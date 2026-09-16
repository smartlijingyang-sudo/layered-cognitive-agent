"""``fold_run_health`` — pure fold from a run's spine to a
``RunHealthReport`` (PR-1 / Task 1.4).

Upholds AGENTS.md §3 C8 (determinism) and §3 C13 (information bloodline
closure). The fold function:

- reads one spine file (``<run_id>.spine.jsonl``, line-delimited JSON,
  one event per line);
- discovers the eight registered derivers via
  ``importlib.metadata.entry_points(group="lca.health_derivers")``;
- calls each deriver's ``evaluate(events)`` and concatenates the
  returned ``RunHealthCondition`` list;
- aggregates the conditions into a ``RunHealthSummary`` whose
  ``by_type`` is the worst status per ``type``;
- constructs and returns the frozen ``RunHealthReport``.

The fold has NO other I/O: no network, no logging to external sinks,
no clock reading beyond ``time.time()`` for ``generated_at`` (the
only seam-injected non-determinism per AGENTS.md §3 C8).

Consumers (the four PR-1 surfaces) call ``fold_run_health(spine_path)``
and read ``RunHealthReport.model_dump(mode="json")``. No consumer
imports a specific deriver; the registry is the source of truth.
"""

from __future__ import annotations

import importlib.metadata
import json
import time
from pathlib import Path

from lca.contracts.observability.health.condition import (
    RunHealthCondition,
    RunHealthStatus,
)
from lca.contracts.observability.health.deriver import HealthDeriver
from lca.contracts.observability.health.report import (
    RunHealthReport,
    RunHealthSummary,
)
from lca.plugins.observability.health.derivers._spine import (
    SpineEvent,
    parse_run_id,
)

# Status severity priority for the worst-status wins aggregation.
# Higher rank = worse. ``failed`` is the worst; ``ok`` is the best.
_STATUS_SEVERITY: dict[RunHealthStatus, int] = {
    "ok": 0,
    "unknown": 1,
    "degraded": 2,
    "failed": 3,
}


def _discover_derivers() -> tuple[HealthDeriver, ...]:
    """Discover health derivers via Python entry points.

    Each deriver is registered in ``pyproject.toml`` under the
    ``lca.health_derivers`` group. The fold function does not import
    any specific deriver — it only knows the ``HealthDeriver`` Protocol.

    This mirrors k8s admission-webhook / OTel SDK Plugin / pluggy
    patterns: the registry is the source of truth, not the fold file.
    """
    eps = importlib.metadata.entry_points(group="lca.health_derivers")
    return tuple(ep.load()() for ep in eps)


# Module-level cache; ``fold_run_health`` is called per-run, no churn.
_DERIVERS: tuple[HealthDeriver, ...] = _discover_derivers()


def _normalize_event(rec: dict[str, object]) -> SpineEvent | None:
    """Normalize one on-disk spine record into the shape derivers expect.

    Real audit-run spines do NOT carry ``run_id`` at the top level —
    the producer puts it in ``payload`` for a subset of events and
    otherwise leaves it implicit in the ``event_id`` prefix
    (``run_<id>:<seq>``). The original fold required a top-level
    ``run_id`` and silently dropped every event whose producer
    omitted it, producing all-``unknown`` reports.

    Resolution order for ``run_id``:

    1. ``parse_run_id(event_id)`` — every event with a well-formed
       ``run_<id>:<seq>`` event_id carries it here.
    2. ``payload["run_id"]`` — fallback for legacy / partial producers
       that duplicate the run_id into the payload.

    Returns ``None`` for records missing ``event_id`` / ``ts`` /
    ``execution_point`` (the spine EP closed-set is owned by the
    producer; the fold only filters structurally-malformed lines).
    """
    event_id_raw = rec.get("event_id")
    ts_raw = rec.get("ts")
    ep_raw = rec.get("execution_point")
    if not isinstance(event_id_raw, str) or not event_id_raw:
        return None
    if not isinstance(ts_raw, str) or not ts_raw:
        return None
    if not isinstance(ep_raw, str) or not ep_raw:
        return None

    payload_obj = rec.get("payload")
    payload: dict[str, object] = dict(payload_obj) if isinstance(payload_obj, dict) else {}

    parsed = parse_run_id(event_id_raw)
    run_id = parsed or str(payload.get("run_id") or "")

    return SpineEvent(
        event_id=event_id_raw,
        ts=ts_raw,
        run_id=run_id,
        execution_point=ep_raw,
        payload=payload,
    )


def _read_spine_events(path: Path) -> list[SpineEvent]:
    """Read line-delimited JSON spine events from ``path``.

    Missing file or empty file -> empty list. Malformed lines are
    skipped silently (the producer is the SSOT; the fold never raises
    on a producer glitch — it just sees fewer events and reports
    ``unknown`` for the affected dimensions). Real audit-run spines
    also lack a top-level ``run_id`` field; ``_normalize_event``
    synthesizes it from the ``event_id`` prefix.
    """
    if not path.exists():
        return []
    out: list[SpineEvent] = []
    with path.open("rb") as fp:
        for raw in fp:
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                rec = json.loads(stripped)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(rec, dict):
                continue
            normalized = _normalize_event(rec)
            if normalized is not None:
                out.append(normalized)
    return out


def _extract_run_id(events: list[SpineEvent]) -> str:
    """Extract the run_id from the first event; empty string if none."""
    if not events:
        return ""
    return events[0]["run_id"]


def _summarize(conditions: list[RunHealthCondition]) -> RunHealthSummary:
    """Aggregate a list of conditions into a ``RunHealthSummary``.

    ``by_type`` maps each ``RunHealthCondition.type`` to its worst
    status (priority: ``failed`` > ``degraded`` > ``unknown`` > ``ok``).
    Counters are the partition of ``conditions`` by status.
    """
    by_type: dict[str, RunHealthStatus] = {}
    counts: dict[RunHealthStatus, int] = {
        "ok": 0,
        "degraded": 0,
        "failed": 0,
        "unknown": 0,
    }
    for c in conditions:
        counts[c.status] += 1
        current = by_type.get(c.type)
        if current is None or _STATUS_SEVERITY[c.status] > _STATUS_SEVERITY[current]:
            by_type[c.type] = c.status
    return RunHealthSummary(
        conditions_ok=counts["ok"],
        conditions_degraded=counts["degraded"],
        conditions_failed=counts["failed"],
        conditions_unknown=counts["unknown"],
        by_type=by_type,
    )


def fold_run_health(spine_path: Path) -> RunHealthReport:
    """Fold one run's spine into a ``RunHealthReport``.

    Pure with respect to the spine file: deterministic for a given
    input (modulo ``generated_at``). Reads the spine, runs every
    registered deriver, aggregates the conditions, returns the
    frozen report.

    Spec §10.5 properties:
    1. Determinism modulo ``generated_at``.
    2. ``len(conditions) >= 6`` for any non-empty run (each deriver
       returns at least 1 condition).
    3. Every condition has ``len(evidence_refs) >= 1`` (enforced by
       the derivers themselves; the fold does not re-validate).
    4. ``evidence_refs[*].execution_point`` is the spine EP string
       the producer wrote; the closed-set lives in the producer
       contract, not in the fold.
    """
    events = _read_spine_events(spine_path)
    conditions: list[RunHealthCondition] = []
    for deriver in _DERIVERS:
        conditions.extend(deriver.evaluate(events))
    return RunHealthReport(
        schema_version="1.0",
        run_id=_extract_run_id(events),
        generated_at=time.time(),
        conditions=tuple(conditions),
        summary=_summarize(conditions),
    )


def _worst_status(report: RunHealthReport) -> RunHealthStatus:
    """Return the worst status across all conditions.

    Priority: ``failed`` > ``degraded`` > ``unknown`` > ``ok``. Used by
    the post-create consumer to compute ``health_summary.overall``.
    Empty ``conditions`` -> ``"unknown"`` (no evidence either way).
    """
    if not report.conditions:
        return "unknown"
    worst: RunHealthStatus = "ok"
    for c in report.conditions:
        if _STATUS_SEVERITY[c.status] > _STATUS_SEVERITY[worst]:
            worst = c.status
    return worst


__all__ = [
    "_DERIVERS",
    "_discover_derivers",
    "_extract_run_id",
    "_normalize_event",
    "_read_spine_events",
    "_summarize",
    "_worst_status",
    "fold_run_health",
]
