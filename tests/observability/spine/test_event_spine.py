"""Tests for EventSpine (Task 1.5).

ADR-0186 更新:spine_port_append 现在要求 Session hook 绑定。
conftest.py 提供 sync_passthrough_hook fixture 模拟旧同步路径行为。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from lca.infrastructure.observability.spine.context import (
    SpineContext,
)
from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.event_spine import EventSpine
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink


def test_event_spine_writes_event(tmp_path: Path):
    SpineContext.set_run("r1")
    fs = FileSink(tmp_path, run_id="r1")
    spine = EventSpine(sinks=[fs], subscribers=[])
    span = SpineContext.push_span("brain.think.start")
    rec = spine.append(
        execution_point="brain.think.start",
        channel="fact",
        caller_payload={"x": 1},
        span_ctx=span,
    )
    spine.close()
    # ADR-0169 PR-27:默认 = <run_id>.spine.jsonl
    lines = (tmp_path / "r1.spine.jsonl").read_text().splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["execution_point"] == "brain.think.start"
    assert obj["sequence"] >= 1
    assert obj["causality_id"].startswith("sha256:")


def test_event_spine_fd1_raises_to_business(tmp_path: Path):
    """FileSink error propagates as FD-1 (fail-fast)."""
    fs = FileSink(tmp_path, run_id="r1")
    spine = EventSpine(sinks=[fs], subscribers=[])
    # Replace the fd with an invalid one — writes will raise OSError
    fs._fd = -1  # type: ignore[attr-defined]
    fs._closed = False  # type: ignore[attr-defined]
    span = SpineContext.push_span("brain.think.start")
    # Sequence counter is per-process ContextVar; tests run in same
    # interpreter, so don't assert exact value here. Just assert FD-1.
    with pytest.raises(OSError):
        spine.append(
            execution_point="brain.think.start",
            channel="fact",
            caller_payload={},
            span_ctx=span,
        )
    SpineContext.pop_span("brain.think.start")  # cleanup


def test_event_spine_fd2_deriver_failure_contained(tmp_path: Path):
    """FD-2: deriver exception does NOT block business."""
    fs = FileSink(tmp_path, run_id="r1")
    captured: list[EventRecord] = []

    def good(rec: EventRecord) -> None:
        captured.append(rec)

    def bad(rec: EventRecord) -> None:
        raise RuntimeError("deriver boom")

    spine = EventSpine(sinks=[fs], subscribers=[good, bad])
    span = SpineContext.push_span("brain.think.start")
    rec = spine.append(
        execution_point="brain.think.start",
        channel="fact",
        caller_payload={},
        span_ctx=span,
    )
    spine.close()
    # good deriver saw the event
    assert len(captured) == 1
    assert captured[0].sequence == rec.sequence
    # event still landed on disk(ADR-0169 PR-27 默认 = <run_id>.spine.jsonl)
    assert (tmp_path / "r1.spine.jsonl").exists()


def test_event_spine_multiple_events_monotonic_seq(tmp_path: Path):
    fs = FileSink(tmp_path, run_id="r1")
    spine = EventSpine(sinks=[fs], subscribers=[])
    span = SpineContext.push_span("kernel.run.start")
    sequences = [
        spine.append(
            execution_point="kernel.run.start",
            channel="control",
            caller_payload={"i": i},
            span_ctx=span,
        ).sequence
        for i in range(5)
    ]
    spine.close()
    # strictly increasing; not asserting exact values because ContextVar
    # state may carry over from earlier tests in the same pytest run.
    assert sequences == sorted(set(sequences))
    assert all(b > a for a, b in zip(sequences, sequences[1:]))
    assert all(s >= 1 for s in sequences)


def test_event_spine_subscribe_returns_disposer(tmp_path: Path):
    fs = FileSink(tmp_path, run_id="r1")
    spine = EventSpine(sinks=[fs])
    seen: list[Any] = []

    def d(rec):
        seen.append(rec)

    dispose = spine.subscribe(d)
    span = SpineContext.push_span("brain.think.start")
    spine.append(
        execution_point="brain.think.start",
        channel="fact",
        span_ctx=span,
    )
    assert len(seen) == 1
    dispose()
    spine.append(
        execution_point="brain.think.start",
        channel="fact",
        span_ctx=span,
    )
    assert len(seen) == 1  # disposer removed it
    spine.close()


def test_event_spine_requires_at_least_one_sink():
    with pytest.raises(ValueError, match="at least one sink"):
        EventSpine(sinks=[])
