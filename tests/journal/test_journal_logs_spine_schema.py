"""Regression tests for ``journal logs`` spine-schema rendering.

Production spine ledgers (``traces/runs/<id>/<run_id>.spine.jsonl``) carry
``event_id`` of the form ``<run_id>:<seq>`` and an ISO ``ts`` field; they do
NOT carry the legacy ``sequence`` / ``when`` fields that the renderer used to
read. These tests pin the dual-schema handling so ``seq`` and the timestamp
are never ``0`` / empty again on real runs.
"""

from __future__ import annotations

from lca.infrastructure.cli.commands.journal import (
    spine_event_seq,
    spine_event_when,
)
from lca.infrastructure.cli.commands.journal.journal import _render_event


def test_spine_event_seq_derives_from_event_id() -> None:
    """``event_id`` of the form ``<run_id>:<seq>`` yields the sequence."""
    event = {"event_id": "run_41fbd76ce118:1985"}
    assert spine_event_seq(event) == 1985


def test_spine_event_seq_falls_back_to_legacy_sequence_field() -> None:
    """Legacy ``EventRecord``-shaped events still expose ``sequence``."""
    event = {"event_id": "no-colon", "sequence": 7}
    assert spine_event_seq(event) == 7
    event_no_id = {"sequence": 9}
    assert spine_event_seq(event_no_id) == 9


def test_spine_event_seq_returns_zero_when_unparseable() -> None:
    assert spine_event_seq({}) == 0
    assert spine_event_seq({"event_id": "no-colon"}) == 0
    assert spine_event_seq({"event_id": "run_x:abc"}) == 0


def test_spine_event_when_prefers_ts_over_when() -> None:
    event = {"ts": "2026-09-21T06:33:27.785901+00:00", "when": "ignored"}
    assert spine_event_when(event) == "2026-09-21T06:33:27.785901+00:00"
    legacy = {"when": "2026-09-01T00:00:00+00:00"}
    assert spine_event_when(legacy) == "2026-09-01T00:00:00+00:00"


def test_render_event_production_schema_shows_real_seq_and_ts() -> None:
    """A production spine event renders its derived seq and timestamp."""
    event = {
        "event_id": "run_x:42",
        "ts": "2026-09-21T06:33:27.785901+00:00",
        "execution_point": "kernel.run.start",
        "channel": "fact",
    }
    line = _render_event(event, verbose=False)
    assert "seq=42" in line
    assert line.startswith("2026-09-21T06:33:27.785")


def test_render_event_legacy_schema_still_works() -> None:
    """Legacy events (``sequence`` / ``when``) keep rendering correctly."""
    event = {
        "sequence": 7,
        "when": "2026-09-01T00:00:00+00:00",
        "execution_point": "brain.think.start",
        "channel": "fact",
    }
    line = _render_event(event, verbose=False)
    assert "seq=7" in line
    assert line.startswith("2026-09-01T00:00:00+00")
