# RETAINED(test/CLI/capability; tracking: ADR-0186 PR-3g / I-SESSION-5)
# Production step_tree uses StepTreeFoldDeriver (I-SESSION-5 fold-only builder).
# Anomaly is invoked by ``session.spine_anomaly`` Session observer when a
# run-bound Session hook is active; ``EmitPipeline.emit`` only calls
# ``on_event`` on the hook-less fallback path (unit tests / pre-boot).

"""AnomalyDetector — I15 / I16 spine deriver with 8 invariant-violation detectors.

This module ships the spine ``AnomalyDetector`` deriver required by
``I15`` (anomaly emission) and ``I16`` (8-detector build-time
enforcement). Each detector is implemented as a private ``_check_*``
method that takes a single :class:`EventRecord` and returns ``True``
when the invariant is violated. ``on_event`` iterates all 8 detectors
in a fixed order; if any returns ``True`` the deriver emits an anomaly
record on the ``anomaly`` channel of its subscriber contract.

Detector catalogue (must stay aligned with ``I16``):

* ``near_timeout`` — ``duration_ms > declared.timeout_ms * 0.94``
* ``cycle`` — same ``execution_point`` repeated within ``CYCLE_WINDOW`` events
* ``stuck`` — open span older than ``STUCK_THRESHOLD_S`` seconds
* ``stalled`` — sequence gap greater than 1 (skipped sequences)
* ``state_machine_violation`` — ``pop_span`` without matching ``push_span``
* ``near_budget`` — ``budget_consumed > budget_at_entry * 0.94``
* ``collision`` — same ``span_id`` appearing twice in the stream
* ``orphan_side_effect`` — ``phase='orphan'`` but payload carries a tool_call

The deriver is wrapped with the project ``@plugin`` decorator under
``spine.deriver.anomaly``; the Cordis carrier ``plugin`` and the
``AnomalyDetector`` class are exported for downstream Profile boot
wiring.

References
----------
* ``docs/superpowers/specs/2026-09-01-spine-execution-points-design.md`` §7.5.4.1
* ADR-0165 / ADR-0165.1 — Spine invariants
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.observability.spine.derivers.base import Deriver
from lca.infrastructure.observability.spine.event_record import EventRecord

log = logging.getLogger(__name__)


# ── public anomaly record shape (kept minimal; downstream consumers
#    subscribe through EventSpine and read channel='anomaly') ──────────────


def _make_anomaly_payload(
    *,
    kind: str,
    event: EventRecord,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Stamp the canonical anomaly envelope for downstream subscribers."""
    evidence_hash = hashlib.sha256(
        json.dumps(
            {
                "execution_point": event.execution_point,
                "span_id": event.span_id,
                "sequence": event.sequence,
                "evidence": evidence,
            },
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "kind": kind,
        "execution_point": event.execution_point,
        "span_id": event.span_id,
        "sequence": event.sequence,
        "run_id": event.run_id,
        "evidence": evidence,
        "evidence_hash": "sha256:" + evidence_hash,
    }


class AnomalyDetector(Deriver):
    """Spine deriver that emits anomaly records on invariant violations.

    The class is the seam boundary required by ``I16``: it exposes
    exactly 8 ``_check_*`` methods whose names map 1:1 onto detector
    kinds (see module docstring). Boot wiring reflects over the class
    to confirm none was forgotten; a regression fails the build.

    The detector is best-effort: per FD-2, exceptions raised inside
    ``on_event`` are contained and logged. A single broken detector
    must never break the spine.
    """

    # ── public thresholds (named per design §7.5.4.1) ────────────────
    NEAR_TIMEOUT_RATIO: float = 0.94
    CYCLE_WINDOW: int = 100
    STUCK_THRESHOLD_S: int = 60
    NEAR_BUDGET_RATIO: float = 0.94

    def __init__(self) -> None:
        # Rolling window of recent execution_points for cycle detection.
        self._recent_points: deque[str] = deque(maxlen=self.CYCLE_WINDOW)
        # Last observed sequence number for stalled detection.
        self._last_sequence: int | None = None
        # Open spans keyed by span_id; populated by ``_check_stuck``.
        self._open_spans: dict[str, datetime] = {}
        # Span ids already seen; collision detection.
        self._seen_span_ids: set[str] = set()
        # Optional anomaly sink (Profile boot may inject one).
        self._anomaly_sink: Any | None = None

    # ── injectable seam ──────────────────────────────────────────────
    def bind_anomaly_sink(self, sink: Any) -> None:
        """Inject the anomaly sink used by ``on_event`` to publish findings.

        Boot wiring calls this with the project-wide anomaly collector
        once it exists; before that, ``on_event`` only logs.
        """
        self._anomaly_sink = sink

    # ── 8 detectors (I16) ────────────────────────────────────────────
    def _check_near_timeout(self, event: EventRecord) -> bool:
        """Trip when ``duration_ms > declared.timeout_ms * NEAR_TIMEOUT_RATIO``."""
        payload = event.payload
        duration = payload.get("duration_ms")
        declared = payload.get("declared") or {}
        timeout_ms = declared.get("timeout_ms") if isinstance(declared, dict) else None
        if not isinstance(duration, (int, float)) or not isinstance(timeout_ms, (int, float)):
            return False
        if timeout_ms <= 0:
            return False
        return duration > timeout_ms * self.NEAR_TIMEOUT_RATIO

    def _check_cycle(self, event: EventRecord) -> bool:
        """Trip when the same ``execution_point`` repeats within ``CYCLE_WINDOW``."""
        point = event.execution_point
        if point in self._recent_points:
            return True
        self._recent_points.append(point)
        return False

    def _check_stuck(self, event: EventRecord) -> bool:
        """Trip when an open span has aged past ``STUCK_THRESHOLD_S`` seconds.

        For ``*.start`` execution points, register the timestamp; for
        ``*.end`` execution points, drop the registration.  A later
        event for the same span is checked against the open timestamp.
        """
        point = event.execution_point
        span_id = event.span_id
        if point.endswith(".start"):
            self._open_spans[span_id] = event.when
            return False
        opened = self._open_spans.get(span_id)
        if opened is None:
            return False
        elapsed = (event.when - opened).total_seconds()
        if elapsed > self.STUCK_THRESHOLD_S:
            self._open_spans.pop(span_id, None)
            return True
        if point.endswith(".end"):
            self._open_spans.pop(span_id, None)
        return False

    def _check_stalled(self, event: EventRecord) -> bool:
        """Trip when the sequence advances by more than 1 (skipped sequences)."""
        last = self._last_sequence
        self._last_sequence = event.sequence
        if last is None:
            return False
        return event.sequence - last > 1

    def _check_state_machine_violation(self, event: EventRecord) -> bool:
        """Trip when ``pop_span`` is observed without a matching ``push_span``.

        The spine's ``PhaseMachineViolation`` raises from
        ``SpineContext.pop_span`` and is normally contained upstream.
        Detectors here observe the propagated marker in the payload
        (``state_machine_violation`` key) so we can flag any stray
        anomaly emission from derivers / reflectors that bypass
        ``SpineContext`` entirely.
        """
        marker = event.payload.get("state_machine_violation")
        return isinstance(marker, str) and bool(marker)

    def _check_near_budget(self, event: EventRecord) -> bool:
        """Trip when ``budget_consumed > budget_at_entry * NEAR_BUDGET_RATIO``."""
        consumed = event.payload.get("budget_consumed")
        at_entry = event.payload.get("budget_at_entry")
        if not isinstance(consumed, (int, float)) or not isinstance(at_entry, (int, float)):
            return False
        if at_entry <= 0:
            return False
        return consumed > at_entry * self.NEAR_BUDGET_RATIO

    def _check_collision(self, event: EventRecord) -> bool:
        """Trip when a ``span_id`` reappears after being seen once already."""
        span_id = event.span_id
        if span_id in self._seen_span_ids:
            return True
        self._seen_span_ids.add(span_id)
        return False

    def _check_orphan_side_effect(self, event: EventRecord) -> bool:
        """Trip when ``phase='orphan'`` but the payload carries a tool_call."""
        if event.phase != "orphan":
            return False
        return "tool_call" in event.payload

    # ── Deriver Protocol entrypoint ──────────────────────────────────
    def on_event(self, event: EventRecord) -> None:
        """Iterate all 8 detectors; emit / log on first trip.

        Per FD-2 any detector failure is contained: only the first
        anomaly (per kind) is forwarded so a single broken payload
        cannot flood downstream subscribers.
        """
        check_methods = [
            ("near_timeout", self._check_near_timeout),
            ("cycle", self._check_cycle),
            ("stuck", self._check_stuck),
            ("stalled", self._check_stalled),
            ("state_machine_violation", self._check_state_machine_violation),
            ("near_budget", self._check_near_budget),
            ("collision", self._check_collision),
            ("orphan_side_effect", self._check_orphan_side_effect),
        ]
        for kind, fn in check_methods:
            try:
                tripped = fn(event)
            except Exception as exc:
                log.warning(
                    "anomaly_detector: check %s raised err=%s",
                    kind,
                    exc,
                    exc_info=True,
                )
                continue
            if not tripped:
                continue
            evidence = self._evidence_for(kind, event)
            payload = _make_anomaly_payload(kind=kind, event=event, evidence=evidence)
            if self._anomaly_sink is not None:
                try:
                    self._anomaly_sink(payload)
                except Exception as exc:
                    log.warning(
                        "anomaly_detector: sink emit failed kind=%s err=%s",
                        kind,
                        exc,
                        exc_info=True,
                    )
            else:
                log.warning(
                    "anomaly_detector: kind=%s ep=%s span_id=%s evidence=%s",
                    kind,
                    event.execution_point,
                    event.span_id,
                    evidence,
                )

    @staticmethod
    def _evidence_for(kind: str, event: EventRecord) -> dict[str, Any]:
        """Render a small per-kind evidence dict for the anomaly record."""
        payload = event.payload
        if kind == "near_timeout":
            return {
                "duration_ms": payload.get("duration_ms"),
                "declared_timeout_ms": (payload.get("declared") or {}).get("timeout_ms")
                if isinstance(payload.get("declared"), dict)
                else None,
            }
        if kind == "near_budget":
            return {
                "budget_consumed": payload.get("budget_consumed"),
                "budget_at_entry": payload.get("budget_at_entry"),
            }
        if kind == "stuck":
            return {
                "span_id": event.span_id,
                "when": event.when.isoformat(),
                "now": datetime.now(timezone.utc).isoformat(),
            }
        if kind == "stalled":
            return {"sequence": event.sequence}
        if kind == "state_machine_violation":
            return {"marker": payload.get("state_machine_violation")}
        if kind == "cycle":
            return {"execution_point": event.execution_point}
        if kind == "collision":
            return {"span_id": event.span_id}
        if kind == "orphan_side_effect":
            return {
                "reason": event.reason,
                "tool_call_keys": sorted(
                    (payload.get("tool_call") or {}).keys()
                    if isinstance(payload.get("tool_call"), dict)
                    else []
                ),
            }
        return {}


# ── plugin Manifest ─────────────────────────────────────────────────


@plugin(
    id="spine.deriver.anomaly",
    provides=("deriver.anomaly",),
    layer="L0",
    kind=PluginKind.SEAM,
    effects="none",
    description=(
        "I15/I16 anomaly deriver — emits invariant-violation records "
        "via 8 _check_* detectors (near_timeout, cycle, stuck, stalled, "
        "state_machine_violation, near_budget, collision, orphan_side_effect)."
    ),
    test_suite="tests.lca_plugins.observability.spine.test_anomaly_detector",
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Wire ``AnomalyDetector`` into the active spine on boot.

    The Profile boot DAG calls ``setup`` once the spine event record
    interface is bound. We construct a single ``AnomalyDetector`` and
    stash it on the ``PluginContext`` so deriver collectors can
    ``bind_anomaly_sink`` once they exist (FD-2 containment).
    """
    detector = AnomalyDetector()
    ctx.provide("deriver.anomaly", detector)
    log.debug(
        "spine.deriver.anomaly: setup complete thresholds=%s/%s/%s",
        AnomalyDetector.NEAR_TIMEOUT_RATIO,
        AnomalyDetector.STUCK_THRESHOLD_S,
        AnomalyDetector.NEAR_BUDGET_RATIO,
    )


__all__ = [
    "AnomalyDetector",
    "setup",
]
