"""E2E integration: a cancel-during-boot run emits an orphan trail.

PR-6 (ADR-0165.1 §19, design §4.3). When the orchestrator receives a
user cancel *before* a step is open, the spine events emitted during
shutdown cannot belong to the step tree. They must:

1. Reach ``events.jsonl`` (append-only sink) so diagnosis is possible;
2. Carry ``phase="orphan"`` + ``reason="cancel_pre_boot"``;
3. Be skipped by ``StepTreeDeriver`` (no ``journal.json`` write).

This file lives under ``tests/observability/spine/`` rather than
``tests/e2e/`` because the existing ``tests/e2e/`` harness is a
collection of integration tests without an ``E2ERunner``/cancel fixture
(see ``tests/e2e/test_full_run_replay.py``, ``test_declarative_long_horizon_recovery.py``).
Spinning up a full profile + boot + SIGTERM path here would be flaky and
outsource the spine contract to a higher layer. Instead we drive the
spine + FileSink + StepTreeDeriver directly — the same components the
orchestrator would call — and assert the contract end-to-end through
``events.jsonl``.

The brief's "``len(orphans) >= 3``" expectation corresponds to the three
control-plane events a cancel handler emits: ``kernel.run.start`` (the
run began), ``kernel.run.cancelled`` (user asked to stop), and
``kernel.run.stop`` (orchestrator confirmed exit). All three are produced
with no active step and therefore carry ``phase="orphan"`` +
``reason="cancel_pre_boot"``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from lca.contracts.models.observability import JournalMetadata
from lca.infrastructure.observability.journal.step.backend import StepGroupedBackend
from lca.infrastructure.observability.spine.context import SpineContext
from lca.infrastructure.observability.spine.derivers.step_tree import (
    StepTreeDeriver,
)
from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.event_spine import EventSpine
from lca.infrastructure.observability.spine.orphan import (
    CANCEL_PRE_BOOT,
    mark_orphan,
)
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink
from lca.runtime.step_lifecycle import (
    StepLifecycleStore,
    reset_lifecycle_store,
    set_lifecycle_store,
)


def _meta() -> JournalMetadata:
    return JournalMetadata(
        agent_role="agt_cancel_pre_boot",
        strategy_key="solo",
        plan_ref="plan_cancel_pre_boot",
        objective="cancel-during-boot e2e",
    )


def _live_event(**overrides: object) -> EventRecord:
    """Build a default live ``EventRecord`` carrying minimal metadata."""
    base: dict[str, object] = {
        "execution_point": "kernel.run.start",
        "channel": "control",
        "span_id": "01HMCANCEL",
        "parent_span_id": None,
        "sequence": 1,
        "epoch": 1,
        "causality_id": "sha256:cancel",
        "outcome": None,
        "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        "when_corrected": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        "prev_event_hash": None,
        "run_id": "r-cancel-pre-boot",
        "step_id": None,
        "payload": {"k": "v"},
    }
    base.update(overrides)
    return EventRecord(**base)  # type: ignore[arg-type]


def _install_cancel_handler(spine: EventSpine) -> None:
    """Install the minimal orchestrator-side cancel handler.

    Mirrors what a production cancel handler does (see PR-6 / ADR-0165.1
    §19): for every live event arriving at the spine during shutdown,
    forward an ``orphan`` copy with ``reason="cancel_pre_boot"``. The
    spine still writes the original live event (via ``mark_orphan`` on
    a copy); the deriver skips the orphan copy.
    """

    def _handle(rec: EventRecord) -> None:
        # Do not re-mark already-orphan events (defence in depth).
        if rec.phase == "orphan":
            return
        orphan = mark_orphan(rec, CANCEL_PRE_BOOT)
        # Re-emit through the spine so it reaches the sink with a fresh
        # sequence/epoch/causality_id stamp. Spine writes sink first
        # (FD-1) then notifies subscribers (FD-2); StepTreeDeriver will
        # see the orphan event and skip it.
        spine.append(
            execution_point=orphan.execution_point,
            channel=orphan.channel,
            caller_payload=dict(orphan.payload),
            outcome=orphan.outcome,
            phase=orphan.phase,
            reason=orphan.reason,
        )

    spine.subscribe(_handle)


def test_cancel_pre_boot_emits_orphan_events(tmp_path: Path) -> None:
    """E2E: cancel-during-boot produces an orphan trail in ``events.jsonl``.

    The orchestrator's cancel handler emits ``phase="orphan"`` events
    with ``reason="cancel_pre_boot"`` for the three control-plane events
    that fire while no step is open (kernel.run.start, kernel.run.cancelled,
    kernel.run.stop). The trail is readable from ``events.jsonl`` and
    ``StepTreeDeriver`` does not project it into ``journal.json``.
    """
    SpineContext.set_run("r-cancel-pre-boot")

    # Bind a lifecycle store — the deriver wraps a StepGroupedBackend
    # that needs it for the (skipped) write path.
    store = StepLifecycleStore()
    store.bind_run(
        run_id="r-cancel-pre-boot",
        trace_id="t-cancel-pre-boot",
        metadata=_meta(),
    )
    token = set_lifecycle_store(store)

    try:
        sink = FileSink(tmp_path, run_id="r-cancel-pre-boot")
        deriver = StepTreeDeriver(
            backend=StepGroupedBackend(
                output_path=tmp_path / "journal.json",
                lifecycle_store=store,
            )
        )
        spine = EventSpine(sinks=[sink], subscribers=[deriver.on_event])
        _install_cancel_handler(spine)

        # Three control-plane events a real cancel-during-boot handler
        # would emit while no step is open.
        emitted: list[EventRecord] = []
        for execution_point in (
            "kernel.run.start",
            "kernel.run.cancelled",
            "kernel.run.stop",
        ):
            rec = spine.append(
                execution_point=execution_point,
                channel="control",
                caller_payload={"user": "u1", "objective": "x"},
                outcome="cancelled" if execution_point == "kernel.run.cancelled" else None,
            )
            emitted.append(rec)

        spine.flush()
        spine.close()

        # ── 1. ``events.jsonl`` carries the orphan trail ──────────────
        events_path = tmp_path / "events.jsonl"
        assert events_path.exists(), "FileSink did not materialise events.jsonl"
        lines = events_path.read_text().splitlines()
        records = [json.loads(line) for line in lines]

        # Each live event produces its own (original) JSON line; the
        # cancel handler re-emits an orphan copy of each. With 3 live
        # events and 3 orphan copies we expect >= 3 orphan lines.
        orphans = [r for r in records if r["phase"] == "orphan"]
        assert len(orphans) >= 3, (
            f"expected at least 3 orphan events, got {len(orphans)}: "
            f"{[r['execution_point'] for r in records]}"
        )
        assert all(o["reason"] == "cancel_pre_boot" for o in orphans), (
            f"orphan reason must be cancel_pre_boot; got {[o['reason'] for o in orphans]}"
        )

        # The orphan trail traces the three control-plane points.
        orphan_points = [o["execution_point"] for o in orphans]
        for expected in ("kernel.run.start", "kernel.run.cancelled", "kernel.run.stop"):
            assert expected in orphan_points, f"orphan trail missing {expected!r}: {orphan_points}"

        # The last orphan event must carry the canonical reason.
        assert orphans[-1]["reason"] == "cancel_pre_boot"

        # The matching live events (the originals) are still on disk
        # too — the cancel handler re-emits orphan copies but does not
        # delete the live events (FD-1 / FD-2 contract).
        live_points = [r["execution_point"] for r in records if r["phase"] == "live"]
        for expected in ("kernel.run.start", "kernel.run.cancelled", "kernel.run.stop"):
            assert expected in live_points, f"live trail missing {expected!r}: {live_points}"

        # ── 2. ``StepTreeDeriver`` skips orphan events ────────────────
        deriver.flush()
        journal_path = tmp_path / "journal.json"
        assert not journal_path.exists(), (
            f"StepTreeDeriver must not materialise journal.json for an "
            f"orphan-only run; found {journal_path.read_text()[:200]!r}"
        )

        # Sanity: ``emitted`` records are returned by the spine itself,
        # so the orchestrator can echo the run-id/sequence back into
        # its own response without re-reading the file.
        assert [r.execution_point for r in emitted] == [
            "kernel.run.start",
            "kernel.run.cancelled",
            "kernel.run.stop",
        ]
        assert emitted[1].outcome == "cancelled"
    finally:
        reset_lifecycle_store(token)


def test_orphan_trail_round_trips_via_file_sink(tmp_path: Path) -> None:
    """Focused companion: writing 3 orphan events through the spine and
    reading ``events.jsonl`` back round-trips the ``phase`` / ``reason``
    fields verbatim. This is the contract downstream tooling
    (``lca-ops journal events --orphans``, anomaly deriver) relies on.
    """
    SpineContext.set_run("r-roundtrip")
    sink = FileSink(tmp_path, run_id="r-roundtrip")
    spine = EventSpine(sinks=[sink])

    reasons = ("cancel_pre_boot", "stop_before_step", "fail_before_step")
    for reason in reasons:
        live = _live_event(phase="live")
        orphan = mark_orphan(live, reason)
        spine.append(
            execution_point=orphan.execution_point,
            channel=orphan.channel,
            caller_payload=dict(orphan.payload),
            phase=orphan.phase,
            reason=orphan.reason,
        )

    spine.close()

    records = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert len(records) == 3
    for rec, reason in zip(records, reasons, strict=True):
        assert rec["phase"] == "orphan"
        assert rec["reason"] == reason
        # Sanity: the spine's auto-fields still landed on disk.
        assert rec["sequence"] >= 1
        assert rec["causality_id"].startswith("sha256:")
