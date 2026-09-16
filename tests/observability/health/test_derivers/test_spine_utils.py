"""Contract tests for ``lca.plugins.observability.health.derivers._spine``.

The shared parsing helpers in ``_spine`` are consumed by all 8 derivers.
Per spec §10.5 evidence property (3), every condition MUST carry at least
one ``EvidenceRef``; the helpers here are the only sanctioned way to
build one. If these tests fail, every deriver's evidence contract fails
with them — that's the intended blast radius (one fix, one PR).
"""

from __future__ import annotations

import pytest

from lca.contracts.observability.health.evidence_ref import EvidenceRef
from lca.plugins.observability.health.derivers._spine import (
    SpineEvent,
    filter_by_ep,
    group_by_invocation,
    make_evidence_ref,
    parse_observed_at,
    parse_run_id,
    parse_seq,
)


def _event(
    *,
    event_id: str = "run_3383288d63e7:18",
    ts: str = "2026-09-16T02:49:35.837507+00:00",
    run_id: str = "run_3383288d63e7",
    execution_point: str = "phase.perceive.fold",
    payload: dict | None = None,
) -> SpineEvent:
    return SpineEvent(
        event_id=event_id,
        ts=ts,
        run_id=run_id,
        execution_point=execution_point,
        payload=payload if payload is not None else {},
    )


# ---------------------------------------------------------------------------
# parse_run_id / parse_seq
# ---------------------------------------------------------------------------


def test_parse_run_id_strips_seq_suffix() -> None:
    """``run_<id>:<seq>`` -> ``run_<id>``."""
    assert parse_run_id("run_3383288d63e7:18") == "run_3383288d63e7"
    assert parse_run_id("run_3cf6e7c036b3:386") == "run_3cf6e7c036b3"
    assert parse_run_id("run_feb0f21ee770:1452") == "run_feb0f21ee770"


def test_parse_seq_returns_int() -> None:
    """``run_<id>:<seq>`` -> ``int(seq)``."""
    assert parse_seq("run_3383288d63e7:18") == 18
    assert parse_seq("run_3383288d63e7:1") == 1
    assert parse_seq("run_feb0f21ee770:1452") == 1452


def test_parse_seq_rejects_non_integer() -> None:
    """A malformed seq raises ``ValueError`` — fail-loud at the seam."""
    with pytest.raises(ValueError):
        parse_seq("run_3383288d63e7:notanumber")


# ---------------------------------------------------------------------------
# parse_observed_at
# ---------------------------------------------------------------------------


def test_parse_observed_at_round_trips_epoch_seconds() -> None:
    """ISO-8601 with ``+00:00`` offset parses to a positive epoch float."""
    ts = "2026-09-16T02:49:35.837507+00:00"
    assert parse_observed_at(ts) == pytest.approx(1789526975.837507, rel=1e-6)


def test_parse_observed_at_orders_monotonically() -> None:
    """Later timestamps yield larger floats (no day-boundary off-by-ones)."""
    earlier = parse_observed_at("2026-09-16T02:49:35.000000+00:00")
    later = parse_observed_at("2026-09-16T02:50:48.006096+00:00")
    assert later > earlier


# ---------------------------------------------------------------------------
# make_evidence_ref
# ---------------------------------------------------------------------------


def test_make_evidence_ref_round_trips_required_fields() -> None:
    """Every field on the spine event propagates to the EvidenceRef."""
    ev = _event()
    ref = make_evidence_ref(ev)
    assert isinstance(ref, EvidenceRef)
    assert ref.run_id == "run_3383288d63e7"
    assert ref.event_id == "run_3383288d63e7:18"
    assert ref.execution_point == "phase.perceive.fold"
    assert ref.seq == 18
    # spine_path is intentionally empty — fold resolves it post-evaluate.
    assert ref.spine_path == ""


def test_make_evidence_ref_is_frozen() -> None:
    """``EvidenceRef`` is frozen; mutation must raise."""
    ref = make_evidence_ref(_event())
    with pytest.raises(Exception):  # ValidationError from Pydantic frozen
        ref.seq = 999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# filter_by_ep
# ---------------------------------------------------------------------------


def test_filter_by_ep_returns_only_matching_events() -> None:
    """Exact EP match; ordering preserved; non-matches dropped."""
    events = [
        _event(event_id="run_x:1", execution_point="phase.perceive.fold"),
        _event(event_id="run_x:2", execution_point="phase.think.fold"),
        _event(event_id="run_x:3", execution_point="phase.perceive.fold"),
    ]
    out = filter_by_ep(events, "phase.perceive.fold")
    assert [e["event_id"] for e in out] == ["run_x:1", "run_x:3"]


def test_filter_by_ep_no_match_returns_empty() -> None:
    """No matches -> empty list, not None."""
    out = filter_by_ep([_event()], "kernel.run.stop")
    assert out == []


# ---------------------------------------------------------------------------
# group_by_invocation
# ---------------------------------------------------------------------------


def test_group_by_invocation_keys_by_invocation_id() -> None:
    """Multiple events with the same invocation_id land in the same bucket."""
    events = [
        _event(event_id="run_x:1", execution_point="step.tool_call.record",
               payload={"invocation_id": "toolu_abc"}),
        _event(event_id="run_x:2", execution_point="step.tool_call.record",
               payload={"invocation_id": "toolu_abc"}),
        _event(event_id="run_x:3", execution_point="step.tool_call.record",
               payload={"invocation_id": "toolu_def"}),
    ]
    grouped = group_by_invocation(events, "step.tool_call.record")
    assert set(grouped.keys()) == {"toolu_abc", "toolu_def"}
    assert len(grouped["toolu_abc"]) == 2
    assert len(grouped["toolu_def"]) == 1


def test_group_by_invocation_drops_events_without_invocation_id() -> None:
    """Events whose payload lacks ``invocation_id`` are silently skipped.

    This matches the brief: grouping is only meaningful for tool-related
    EPs that carry an invocation_id; other EPs (e.g. ``phase.perceive.fold``)
    should not be passed through this helper.
    """
    events = [
        _event(event_id="run_x:1", execution_point="step.tool_call.record",
               payload={"invocation_id": "toolu_abc"}),
        _event(event_id="run_x:2", execution_point="step.tool_call.record",
               payload={}),  # no invocation_id
        _event(event_id="run_x:3", execution_point="phase.perceive.fold"),
    ]
    grouped = group_by_invocation(events, "step.tool_call.record")
    assert set(grouped.keys()) == {"toolu_abc"}


def test_group_by_invocation_only_matches_target_ep() -> None:
    """Events of other EPs are skipped even if they carry an invocation_id."""
    events = [
        _event(event_id="run_x:1", execution_point="step.tool_call.record",
               payload={"invocation_id": "toolu_abc"}),
        _event(event_id="run_x:2", execution_point="body.sandbox.enter",
               payload={"invocation_id": "toolu_abc"}),
    ]
    grouped = group_by_invocation(events, "step.tool_call.record")
    assert set(grouped.keys()) == {"toolu_abc"}
    assert len(grouped["toolu_abc"]) == 1
    assert grouped["toolu_abc"][0]["execution_point"] == "step.tool_call.record"