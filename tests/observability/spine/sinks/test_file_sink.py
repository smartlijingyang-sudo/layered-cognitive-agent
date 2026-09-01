"""Tests for FileSink (Task 1.4)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink


def _make_rec(**overrides) -> EventRecord:
    base = {
        "execution_point": "brain.think.start",
        "channel": "fact",
        "span_id": "01HM",
        "parent_span_id": None,
        "sequence": 1,
        "epoch": 1,
        "causality_id": "ca",
        "outcome": None,
        "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        "when_corrected": datetime(2026, 9, 1, 12, 0, 0, 100000, tzinfo=timezone.utc),
        "prev_event_hash": None,
        "run_id": "r1",
        "step_id": "s1",
        "payload": {"x": 1},
    }
    base.update(overrides)
    return EventRecord(**base)


def test_file_sink_appends_and_reads_back(tmp_path: Path):
    fs = FileSink(tmp_path, run_id="r1")
    rec = _make_rec()
    fs.write(rec)
    fs.close()
    lines = (tmp_path / "events.jsonl").read_text().splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["execution_point"] == "brain.think.start"


def test_file_sink_oversize_uses_sidecar(tmp_path: Path):
    fs = FileSink(tmp_path, run_id="r1")
    big = "x" * 5000
    rec = _make_rec(payload={"big": big})
    fs.write(rec)
    fs.close()
    # main events.jsonl references offload; a <hash>.json sidecar exists
    sidecars = [p for p in tmp_path.glob("*.json") if p.name != "events.jsonl"]
    assert len(sidecars) == 1
    main_lines = (tmp_path / "events.jsonl").read_text().splitlines()
    main = json.loads(main_lines[0])
    assert "offloaded" in main
    assert main["offloaded"]


def test_file_sink_close_is_idempotent(tmp_path: Path):
    fs = FileSink(tmp_path, run_id="r1")
    fs.close()
    fs.close()  # no error


def test_file_sink_write_after_close_raises(tmp_path: Path):
    fs = FileSink(tmp_path, run_id="r1")
    fs.close()
    import pytest
    with pytest.raises(RuntimeError):
        fs.write(_make_rec())


def test_file_sink_multiple_writes_preserve_order(tmp_path: Path):
    fs = FileSink(tmp_path, run_id="r1")
    for seq in (1, 2, 3, 4, 5):
        fs.write(_make_rec(sequence=seq))
    fs.close()
    lines = (tmp_path / "events.jsonl").read_text().splitlines()
    assert len(lines) == 5
    seqs = [json.loads(line)["sequence"] for line in lines]
    assert seqs == [1, 2, 3, 4, 5]
