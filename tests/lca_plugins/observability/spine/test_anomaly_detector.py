"""Tests for the spine ``AnomalyDetector`` deriver plugin (Task 7.7).

I15 / I16 enforcement: ``AnomalyDetector`` MUST expose exactly 8
``_check_*`` methods — one per detector class — and a build-time
``hasattr`` check on the class confirms none was forgotten during
evolution.

Behavioural coverage here focuses on two detectors whose trip
conditions can be reproduced with minimal fixtures:

* ``_check_near_timeout`` — ``duration_ms > declared.timeout_ms * 0.94``
* ``_check_near_budget`` — ``budget_consumed > budget_at_entry * 0.94``

The remaining 6 detectors have a smaller trip surface but the I16
``hasattr`` reflection test pins their existence so a refactor that
removes any one of them is caught at boot.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from lca.infrastructure.observability.spine.event_record import EventRecord

# ── shared fixtures ──────────────────────────────────────────────────


_BASE_KWARGS: dict[str, object] = {
    "execution_point": "brain.think.start",
    "channel": "fact",
    "span_id": "lca-span-00000001",
    "parent_span_id": None,
    "sequence": 1,
    "epoch": 1,
    "causality_id": "sha256:abc",
    "outcome": None,
    "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
    "when_corrected": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
    "prev_event_hash": None,
    "run_id": "r-test",
    "step_id": "s-test",
    "payload": {},
}


def _make_event(**overrides: object) -> EventRecord:
    kwargs = dict(_BASE_KWARGS)
    kwargs.update(overrides)
    return EventRecord(**kwargs)  # type: ignore[arg-type]


# ── I16: 8-detector reflection enforcement ──────────────────────────


def test_anomaly_detector_has_exactly_8_check_methods() -> None:
    """I16 build-time enforcement: exactly 8 ``_check_*`` methods must exist.

    Method names map 1:1 to detector kinds via the
    ``_check_<kind>`` convention; boot wiring reflects over the class
    to confirm none was forgotten. A regression here fails the build.
    """
    from lca.plugins.observability.spine.derivers.anomaly import AnomalyDetector

    expected = {
        "near_timeout",
        "cycle",
        "stuck",
        "stalled",
        "state_machine_violation",
        "near_budget",
        "collision",
        "orphan_side_effect",
    }
    actual = {m.replace("_check_", "") for m in dir(AnomalyDetector) if m.startswith("_check_")}
    assert actual == expected, (
        f"I16 violation: AnomalyDetector exposes {actual!r}; expected {expected!r}"
    )


def test_anomaly_detector_satisfies_deriver_protocol() -> None:
    """Structural typing: ``AnomalyDetector`` must implement the Deriver Protocol."""
    from lca.infrastructure.observability.spine.derivers.base import Deriver
    from lca.plugins.observability.spine.derivers.anomaly import AnomalyDetector

    detector = AnomalyDetector()
    assert isinstance(detector, Deriver)
    assert callable(detector.on_event)


# ── detector behaviour: _check_near_timeout ─────────────────────────


def test_check_near_timeout_trips_when_duration_exceeds_threshold() -> None:
    """Trip when ``duration_ms > declared.timeout_ms * 0.94``."""
    from lca.plugins.observability.spine.derivers.anomaly import AnomalyDetector

    detector = AnomalyDetector()
    # 100 ms declared budget; 95 ms > 94 ms = 0.94 * 100 → trip.
    event = _make_event(
        execution_point="brain.think.end",
        payload={"duration_ms": 95, "declared": {"timeout_ms": 100}},
    )
    assert detector._check_near_timeout(event) is True


def test_check_near_timeout_does_not_trip_when_under_threshold() -> None:
    """Below the 0.94 ratio, the detector must NOT trip."""
    from lca.plugins.observability.spine.derivers.anomaly import AnomalyDetector

    detector = AnomalyDetector()
    event = _make_event(
        execution_point="brain.think.end",
        payload={"duration_ms": 50, "declared": {"timeout_ms": 100}},
    )
    assert detector._check_near_timeout(event) is False


def test_check_near_timeout_safe_when_payload_missing_fields() -> None:
    """Missing payload fields must not raise; detector stays silent."""
    from lca.plugins.observability.spine.derivers.anomaly import AnomalyDetector

    detector = AnomalyDetector()
    event = _make_event(payload={})
    assert detector._check_near_timeout(event) is False


# ── detector behaviour: _check_near_budget ──────────────────────────


def test_check_near_budget_trips_when_consumed_exceeds_threshold() -> None:
    """Trip when ``budget_consumed > budget_at_entry * 0.94``."""
    from lca.plugins.observability.spine.derivers.anomaly import AnomalyDetector

    detector = AnomalyDetector()
    event = _make_event(
        payload={"budget_consumed": 95, "budget_at_entry": 100},
    )
    assert detector._check_near_budget(event) is True


def test_check_near_budget_does_not_trip_when_under_threshold() -> None:
    from lca.plugins.observability.spine.derivers.anomaly import AnomalyDetector

    detector = AnomalyDetector()
    event = _make_event(
        payload={"budget_consumed": 50, "budget_at_entry": 100},
    )
    assert detector._check_near_budget(event) is False


# ── detector behaviour: _check_cycle (stateful) ─────────────────────


def test_check_cycle_trips_on_repeated_execution_point_in_window() -> None:
    """The same execution_point within ``CYCLE_WINDOW`` events must trip."""
    from lca.plugins.observability.spine.derivers.anomaly import AnomalyDetector

    detector = AnomalyDetector()
    base = dict(_BASE_KWARGS)
    base["execution_point"] = "brain.think.start"

    # First occurrence: not a cycle yet.
    first = EventRecord(**base)  # type: ignore[arg-type]
    assert detector._check_cycle(first) is False

    # Same execution_point within the rolling window: must trip.
    repeat = EventRecord(**base)  # type: ignore[arg-type]
    assert detector._check_cycle(repeat) is True


def test_check_cycle_resets_when_different_execution_point_observed() -> None:
    """Different execution_points do not constitute a cycle."""
    from lca.plugins.observability.spine.derivers.anomaly import AnomalyDetector

    detector = AnomalyDetector()
    first = _make_event(execution_point="brain.think.start")
    second = _make_event(execution_point="brain.think.end")
    assert detector._check_cycle(first) is False
    assert detector._check_cycle(second) is False


# ── detector behaviour: _check_stuck (open-span elapsed time) ────────


def test_check_stuck_trips_when_span_open_past_threshold() -> None:
    """An open span older than ``STUCK_THRESHOLD_S`` seconds must trip."""
    from lca.plugins.observability.spine.derivers.anomaly import AnomalyDetector

    detector = AnomalyDetector()
    past = datetime(2026, 9, 1, 11, 0, 0, tzinfo=timezone.utc)
    future = past + timedelta(seconds=120)
    detector._open_spans["lca-span-00000099"] = past

    # Use a non-``start`` execution point so the detector does not
    # overwrite the pre-seeded open timestamp with the future ``when``.
    event = _make_event(
        span_id="lca-span-00000099",
        execution_point="synthesizer.merge",
        when=future,
        when_corrected=future,
    )
    assert detector._check_stuck(event) is True


def test_check_stuck_does_not_trip_for_recent_spans() -> None:
    from lca.plugins.observability.spine.derivers.anomaly import AnomalyDetector

    detector = AnomalyDetector()
    started = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
    detector._open_spans["lca-span-00000099"] = started

    event = _make_event(
        span_id="lca-span-00000099",
        when=started + timedelta(seconds=5),
        when_corrected=started + timedelta(seconds=5),
    )
    assert detector._check_stuck(event) is False


# ── detector behaviour: _check_stalled (sequence gap) ────────────────


def test_check_stalled_trips_on_sequence_gap() -> None:
    """A sequence jump greater than 1 indicates a stalled stream."""
    from lca.plugins.observability.spine.derivers.anomaly import AnomalyDetector

    detector = AnomalyDetector()
    detector._last_sequence = 5
    event = _make_event(sequence=10)
    assert detector._check_stalled(event) is True


def test_check_stalled_does_not_trip_on_contiguous_sequence() -> None:
    from lca.plugins.observability.spine.derivers.anomaly import AnomalyDetector

    detector = AnomalyDetector()
    detector._last_sequence = 5
    event = _make_event(sequence=6)
    assert detector._check_stalled(event) is False


# ── detector behaviour: _check_state_machine_violation ───────────────


def test_check_state_machine_violation_trips_on_phase_orphan_without_reason() -> None:
    """EventRecord enforces ``reason`` on ``phase='orphan'``; we simulate a
    payload-side mismatch where the reflection ``reason`` key disagrees
    with the canonical span transition ledger.
    """
    from lca.plugins.observability.spine.derivers.anomaly import AnomalyDetector

    detector = AnomalyDetector()
    # Simulate a state-machine violation: pop_span observed on an
    # empty stack (encoded in payload; we never mutate SpineContext here).
    event = _make_event(
        execution_point="brain.think.end",
        payload={"state_machine_violation": "pop_on_empty_stack"},
    )
    assert detector._check_state_machine_violation(event) is True


# ── detector behaviour: _check_collision (duplicate span_id) ─────────


def test_check_collision_trips_when_span_id_reappears() -> None:
    from lca.plugins.observability.spine.derivers.anomaly import AnomalyDetector

    detector = AnomalyDetector()
    detector._seen_span_ids.add("lca-span-00000042")
    event = _make_event(span_id="lca-span-00000042")
    assert detector._check_collision(event) is True


def test_check_collision_does_not_trip_for_new_span_id() -> None:
    from lca.plugins.observability.spine.derivers.anomaly import AnomalyDetector

    detector = AnomalyDetector()
    event = _make_event(span_id="lca-span-00000043")
    assert detector._check_collision(event) is False


# ── detector behaviour: _check_orphan_side_effect ────────────────────


def test_check_orphan_side_effect_trips_when_orphan_carries_tool_call() -> None:
    """``phase='orphan'`` with a ``tool_call`` payload must trip."""
    from lca.plugins.observability.spine.derivers.anomaly import AnomalyDetector

    detector = AnomalyDetector()
    event = _make_event(
        phase="orphan",
        reason="span_orphaned_after_timeout",
        payload={"tool_call": {"name": "web.search"}},
    )
    assert detector._check_orphan_side_effect(event) is True


def test_check_orphan_side_effect_silent_when_no_tool_call() -> None:
    from lca.plugins.observability.spine.derivers.anomaly import AnomalyDetector

    detector = AnomalyDetector()
    event = _make_event(
        phase="orphan",
        reason="span_orphaned_after_timeout",
        payload={"note": "no tool executed"},
    )
    assert detector._check_orphan_side_effect(event) is False


# ── on_event end-to-end ──────────────────────────────────────────────


def test_on_event_does_not_raise_for_unknown_event() -> None:
    """``on_event`` must never propagate detector failures (FD-2)."""
    from lca.plugins.observability.spine.derivers.anomaly import AnomalyDetector

    detector = AnomalyDetector()
    event = _make_event(payload={"__deliberately_bad__": object()})
    # Should not raise; FD-2 containment.
    detector.on_event(event)


# ── module-level plugin declaration ─────────────────────────────────


def test_module_declares_plugin_with_expected_id() -> None:
    """The ``@plugin`` decorator on ``setup`` must bind ``spine.deriver.anomaly``."""
    from lca.harness.plugin_declaration import definition_from_plugin
    from lca.plugins.observability.spine.derivers import anomaly

    # Touching the module forces the @plugin decorator to attach
    # ``_lca_definition`` onto the carrier.
    assert hasattr(anomaly, "setup")

    definition = definition_from_plugin(anomaly.setup, module=__name__)
    assert definition.id == "spine.deriver.anomaly"
    assert definition.spec.layer == "L0"
    assert "deriver.anomaly" in tuple(definition.provided_capability_keys)


def test_anomaly_detector_class_constants_are_well_named() -> None:
    """Threshold constants must be class-level and well named (review guard)."""
    from lca.plugins.observability.spine.derivers.anomaly import AnomalyDetector

    assert pytest.approx(0.94) == AnomalyDetector.NEAR_TIMEOUT_RATIO
    assert AnomalyDetector.CYCLE_WINDOW == 100
    assert AnomalyDetector.STUCK_THRESHOLD_S == 60
    assert pytest.approx(0.94) == AnomalyDetector.NEAR_BUDGET_RATIO
