"""Tests for RunRoutingFileSink demux."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.sinks.routing_file_sink import (
    RunRoutingFileSink,
)


def _rec(*, run_id: str, ep: str = "kernel.run.start") -> EventRecord:
    now = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
    return EventRecord(
        execution_point=ep,
        channel="control",
        span_id="01",
        parent_span_id=None,
        sequence=1,
        epoch=1,
        causality_id="ca",
        outcome=None,
        when=now,
        when_corrected=now,
        prev_event_hash=None,
        run_id=run_id,
        step_id=None,
        payload={},
    )


def test_boot_ids_go_to_boot_file(tmp_path: Path) -> None:
    boot = tmp_path / "spine" / "boot-events.jsonl"
    runs = tmp_path / "traces" / "runs"
    sink = RunRoutingFileSink(boot_path=boot, runs_root=runs)
    try:
        sink.write(_rec(run_id="boot", ep="kernel.boot.start"))
        sink.write(_rec(run_id="default-run", ep="transport.route.enter"))
        sink.write(_rec(run_id="", ep="transport.route.exit"))
    finally:
        sink.close()

    lines = boot.read_text().splitlines()
    assert len(lines) == 3
    # ADR-0169 PR-27:默认 = <run_id>.spine.jsonl,旧 events.jsonl 不再出现
    assert not any(runs.glob("*/events.jsonl"))
    assert not any(runs.glob("*/spine.jsonl"))


def test_real_run_id_goes_to_traces_runs(tmp_path: Path) -> None:
    boot = tmp_path / "spine" / "boot-events.jsonl"
    runs = tmp_path / "traces" / "runs"
    sink = RunRoutingFileSink(boot_path=boot, runs_root=runs)
    try:
        sink.write(_rec(run_id="run_abc", ep="kernel.run.start"))
        sink.write(_rec(run_id="run_abc", ep="exception.caught"))
    finally:
        sink.close()

    # ADR-0169 PR-27:默认 = <run_id>.spine.jsonl
    path = runs / "run_abc" / "run_abc.spine.jsonl"
    assert path.exists()
    objs = [json.loads(line) for line in path.read_text().splitlines()]
    assert [o["execution_point"] for o in objs] == [
        "kernel.run.start",
        "exception.caught",
    ]
    assert boot.read_text().strip() == ""


def test_close_is_idempotent(tmp_path: Path) -> None:
    sink = RunRoutingFileSink(
        boot_path=tmp_path / "boot.jsonl",
        runs_root=tmp_path / "runs",
    )
    sink.write(_rec(run_id="run_x"))
    sink.close()
    sink.close()
