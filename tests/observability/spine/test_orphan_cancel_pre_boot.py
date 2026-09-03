"""E2E integration: a cancel-during-boot run emits an orphan trail.

PR-6 (ADR-0165.1 §19, design §4.3). When the orchestrator receives a
user cancel *before* a step is open, the spine events emitted during
shutdown cannot belong to the step tree. They must:

1. Reach ``events.jsonl`` (append-only sink) so diagnosis is possible;
2. Carry ``phase="orphan"`` + ``reason="cancel_pre_boot"``;
3. Be skipped by ``StepTreeAccumulatorDeriver`` (no ``journal.json`` step).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from lca.infrastructure.observability.spine.context import SpineContext
from lca.infrastructure.observability.spine.derivers.step_tree_accumulator import (
    StepTreeAccumulatorDeriver,
)
from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.event_spine import EventSpine
from lca.infrastructure.observability.spine.orphan import (
    CANCEL_PRE_BOOT,
    mark_orphan,
)
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink


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
    """每次 live event 经 spine, 转发一个 orphan 副本。"""

    def _handle(rec: EventRecord) -> None:
        if rec.phase == "orphan":
            return
        orphan = mark_orphan(rec, CANCEL_PRE_BOOT)
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
    """E2E: cancel-during-boot produces an orphan trail in events.jsonl。"""
    SpineContext.set_run("r-cancel-pre-boot")
    run_dir = tmp_path / "r-cancel-pre-boot"
    sink = FileSink(tmp_path, run_id="r-cancel-pre-boot")
    deriver = StepTreeAccumulatorDeriver(
        run_id="r-cancel-pre-boot",
        run_dir=run_dir,
        agent_role="agt_cancel_pre_boot",
        strategy_key="solo",
        plan_ref="plan_cancel_pre_boot",
    )
    spine = EventSpine(sinks=[sink], subscribers=[deriver.on_event])
    _install_cancel_handler(spine)

    for execution_point in (
        "kernel.run.start",
        "kernel.run.cancelled",
        "kernel.run.stop",
    ):
        spine.append(
            execution_point=execution_point,
            channel="control",
            caller_payload={"user": "u1", "objective": "x"},
            outcome="cancelled" if execution_point == "kernel.run.cancelled" else None,
        )

    spine.flush()
    spine.close()

    # ADR-0169 PR-27:默认 = <run_id>.spine.jsonl
    events_path = tmp_path / "r-cancel-pre-boot.spine.jsonl"
    assert events_path.exists()
    lines = events_path.read_text().splitlines()
    records = [json.loads(line) for line in lines]

    orphans = [r for r in records if r["phase"] == "orphan"]
    assert len(orphans) >= 3
    assert all(o["reason"] == "cancel_pre_boot" for o in orphans)

    orphan_points = [o["execution_point"] for o in orphans]
    for expected in ("kernel.run.start", "kernel.run.cancelled", "kernel.run.stop"):
        assert expected in orphan_points

    # live 原事件也在 disk
    live_points = [r["execution_point"] for r in records if r["phase"] == "live"]
    for expected in ("kernel.run.start", "kernel.run.cancelled", "kernel.run.stop"):
        assert expected in live_points

    # deriver flush 写入 journal.json, 但没累积 step(全 orphan)
    deriver.flush()
    assert run_dir.joinpath("journal.json").exists()
    doc = deriver.document
    assert doc is not None
    assert len(doc.steps) == 0, (
        "StepTreeAccumulatorDeriver must not accumulate orphan events as steps"
    )


def test_orphan_trail_round_trips_via_file_sink(tmp_path: Path) -> None:
    """3 个 orphan 事件通过 spine → events.jsonl round-trip。"""
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

    # ADR-0169 PR-27:默认 = <run_id>.spine.jsonl
    records = [
        json.loads(line) for line in (tmp_path / "r-roundtrip.spine.jsonl").read_text().splitlines()
    ]
    assert len(records) == 3
    for rec, reason in zip(records, reasons, strict=True):
        assert rec["phase"] == "orphan"
        assert rec["reason"] == reason
        assert rec["sequence"] >= 1
        assert rec["causality_id"].startswith("sha256:")
