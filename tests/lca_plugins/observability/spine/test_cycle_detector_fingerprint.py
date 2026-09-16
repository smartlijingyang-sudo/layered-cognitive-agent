"""AnomalyDetector cycle detector tracks consecutive repeats.

The 2026-09-16 stall: ``phase.act.fold.end`` repeated 879 times in a
row. The old detector only logged a single WARNING per repeat and
provided no signal on how tight the loop was, so operators had to
cross-reference the spine journal to find the actual cycle pattern.

After Fix 3+4 a single spine event answers:
- which EP is in the loop
- how tight the loop is (consecutive count)

Domain-level cycle detection (which tool+args are repeating) is the
job of RepeatToolCallGate — the cycle detector stays EP-only by
design so it does not need to know about Decision / tool_call
schema.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from lca.infrastructure.observability.spine.event.record import EventRecord
from lca.plugins.observability.spine.derivers.anomaly import AnomalyDetector

_BASE_KWARGS: dict[str, object] = {
    "execution_point": "phase.act.fold.end",
    "channel": "live",
    "span_id": "lca-span-00000001",
    "parent_span_id": None,
    "sequence": 1,
    "epoch": 1,
    "causality_id": "sha256:abc",
    "outcome": None,
    "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC),
    "when_corrected": datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC),
    "prev_event_hash": None,
    "run_id": "r-test",
    "step_id": "s-test",
    "payload": {},
}


def _make_event(**overrides: object) -> EventRecord:
    kwargs = dict(_BASE_KWARGS)
    kwargs.update(overrides)
    return EventRecord(**kwargs)  # type: ignore[arg-type]


def _capture_sink() -> tuple[AnomalyDetector, list[dict[str, Any]]]:
    captured: list[dict[str, Any]] = []
    detector = AnomalyDetector()
    detector.bind_anomaly_sink(captured.append)
    return detector, captured


def test_cycle_detector_trips_on_second_consecutive_repeat() -> None:
    detector, sink = _capture_sink()

    for seq in range(1, 4):
        detector.on_event(_make_event(sequence=seq))

    cycles = [p for p in sink if p.get("kind") == "cycle"]
    assert cycles, "expected at least one cycle anomaly"
    first = cycles[0]
    assert first["execution_point"] == "phase.act.fold.end"
    evidence = first["evidence"]
    assert evidence["execution_point"] == "phase.act.fold.end"
    assert evidence["consecutive_count"] >= 2


def test_cycle_detector_does_not_trip_on_different_eps() -> None:
    detector, sink = _capture_sink()

    for seq, ep in enumerate(
        [
            "phase.perceive.fold",
            "phase.think.fold",
            "phase.act.fold",
            "phase.reflect.fold",
        ],
        start=1,
    ):
        detector.on_event(_make_event(execution_point=ep, sequence=seq))

    assert not [p for p in sink if p.get("kind") == "cycle"]


def test_cycle_detector_resets_consecutive_count_on_ep_change() -> None:
    """If the EP changes once, the counter resets — a real loop is the
    pattern ``A A A ...`` (one EP repeating), not ``A B A B ...``.
    """
    detector, sink = _capture_sink()

    for seq in range(1, 5):
        ep = "phase.act.fold.end" if seq % 2 == 1 else "phase.think.fold"
        detector.on_event(_make_event(execution_point=ep, sequence=seq))

    # No consecutive pair of the same EP — no cycle anomaly.
    assert not [p for p in sink if p.get("kind") == "cycle"]
