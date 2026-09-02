"""Regression guard for ADR-0165-i17-traceback-and-coverage.

The architectural layering separated **observation** (journal) from
**control** (reducer / runtime), and the doctor's H2 closure signal
must read from the journal tail. This module pins:

1. ``RUN_FINISHED_EVENTS`` recognises ``kernel.run.stop`` so the doctor
   closes H2 when a run terminated, not only when an SSE-shaped
   ``AgentRunFinished`` event happens to be present (the legacy
   convention did not match the journal ep vocabulary).

2. ``scan_jsonl`` reads ``execution_point`` as an ``event_type``
   fallback. Without this, every journal entry was recorded as
   ``event_type=""`` so the count set never intersected
   ``RUN_FINISHED_EVENTS``.

3. The new journal execution_points are part of the close-set
   whitelist so consumers can subscribe uniformly.

These three together implement §D6 of the ADR. End-to-end behaviour
(``,start`` events with source_location, doctor verdict ``"ok"``) was
verified live against ``run_be654cb3126f`` after the kernel restart;
the unit suite here keeps that contract pinned at the API surface.
"""

from __future__ import annotations

import json
from pathlib import Path

from lca.infrastructure.observability.spine.manifest import EXECUTION_POINTS
from lca.plugins.transport.webserver.handlers.runs.doctor.models import (
    RUN_FINISHED_EVENTS,
)


def test_run_finished_events_recognise_kernel_run_stop() -> None:
    """Doctor must honour the journal vocabulary, not only legacy SSE."""
    assert "kernel.run.stop" in RUN_FINISHED_EVENTS
    # The legacy entries coexist for backward compatibility.
    assert "AgentRunFinished" in RUN_FINISHED_EVENTS
    assert "TeamRunFinished" in RUN_FINISHED_EVENTS


def test_execution_points_whitelist_admits_new_eps() -> None:
    """New journal EPs from the ADR are part of the close-set whitelist."""
    assert "spine.i17.rejected" in EXECUTION_POINTS
    assert "spine.producer.failure" in EXECUTION_POINTS
    assert "phase_graph.instrument.coverage" in EXECUTION_POINTS


def test_scan_jsonl_reads_execution_point(tmp_path: Path) -> None:
    """Doctor's per-line type extraction handles execution_point fallback.

    Regression for: ``event_type`` was always empty for journal-only
    files, so H2 stayed open. See ADR-0165-i17 §D6.
    """
    from lca.plugins.transport.webserver.handlers.runs.doctor.journal import (
        scan_jsonl,
    )

    path = tmp_path / "events.jsonl"
    record = {
        "execution_point": "phase_graph.node.start",
        "channel": "control",
        "sequence": 1,
        "outcome": None,
        "caller_payload": {},
        "phase": "live",
    }
    path.write_text(json.dumps(record), encoding="utf-8")
    scan = scan_jsonl(path)
    assert scan.exists is True
    assert scan.counts.get("phase_graph.node.start") == 1

    path2 = tmp_path / "events2.jsonl"
    record2 = {
        "execution_point": "kernel.run.stop",
        "channel": "control",
        "sequence": 1,
        "outcome": "failure",
        "caller_payload": {},
        "phase": "live",
    }
    path2.write_text(json.dumps(record2), encoding="utf-8")
    scan2 = scan_jsonl(path2)
    assert scan2.counts.get("kernel.run.stop") == 1


def test_existing_finished_events_still_work() -> None:
    """Backward compat: legacy SSE vocabulary still closes H2."""
    # The union semantics: any one of the three token classes is
    # sufficient — pinned so a future contributor doesn't remove the
    # legacy tokens thinking they are dead code.
    assert {
        "AgentRunFinished",
        "TeamRunFinished",
        "kernel.run.stop",
    } <= RUN_FINISHED_EVENTS


def test_scan_jsonl_reads_spine_v3_sequence(tmp_path: Path) -> None:
    """``scan_jsonl`` must honour ``sequence`` (spine v3 envelope).

    Regression for the run ``run_5c0bb23d9e32`` (2026-09-02): the doctor
    reported ``H2.last_seq=0`` while ``H3.last_seq=13`` because
    ``scan_jsonl`` only accepted legacy ``seq`` / ``run_seq`` and missed
    the canonical ``sequence`` field written by spine v3 sinks. This
    pinned the envelope coverage at the doctor layer.
    """
    from lca.plugins.transport.webserver.handlers.runs.doctor.journal import (
        scan_jsonl,
    )

    path = tmp_path / "events.jsonl"
    rows = [
        {"execution_point": "transport.route.exit", "channel": "control", "sequence": 2},
        {"execution_point": "kernel.run.start", "channel": "control", "sequence": 3},
        {"execution_point": "phase_graph.node.start", "channel": "control", "sequence": 7},
        {"execution_point": "phase_graph.node.end", "channel": "control", "sequence": 13},
        {"execution_point": "kernel.run.stop", "channel": "control", "sequence": 21},
    ]
    path.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n",
        encoding="utf-8",
    )
    scan = scan_jsonl(path)
    assert scan.last_seq == 21
    # Sanity: legacy ``seq`` still works.
    legacy = tmp_path / "legacy.jsonl"
    legacy.write_text(
        json.dumps({"execution_point": "x", "channel": "c", "seq": 5}) + "\n",
        encoding="utf-8",
    )
    assert scan_jsonl(legacy).last_seq == 5
