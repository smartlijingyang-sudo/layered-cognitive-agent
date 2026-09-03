"""spine_file_sink 端到端（ADR-0181 PR-8 shim；record 入口 ADR-0183 PR-5）。

record 构造走 build_record() 单一入口；落盘走 SpineSink SSOT 路径；
字节布局 = SpineEventRecord.to_dict() 9 键（sort_keys）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.plugins.events.sinks.spine_file_sink.sink import SpineFileSink
from lca_kernel.events import EventRef
from lca_kernel.events.payloads import SpineEventPayload

_NINE_KEYS = {
    "event_id",
    "category",
    "execution_point",
    "channel",
    "payload",
    "ts",
    "causation_id",
    "prev_event_hash",
    "event_hash",
}


def _ref() -> EventRef:
    return EventRef(
        event_id="evt_test_1",
        category="spine.cognition.brain.perceive.start",
        trace_id="",
        ts=1725350000.0,
    )


def _payload() -> SpineEventPayload:
    return SpineEventPayload(
        execution_point="brain.perceive.start",
        channel="fact",
        payload={"state_id": "s1"},
    )


def test_spine_file_sink_writes_nine_key_record(tmp_path: Path) -> None:
    """build_record 单一入口落盘：9 键 SSOT 布局 + sort_keys 序列化。"""
    sink = SpineFileSink(run_dir=tmp_path)
    try:
        sink(_payload(), _ref())
        sink.flush()
    finally:
        sink.close()

    target = tmp_path / "default-run.spine.jsonl"
    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert set(record) == _NINE_KEYS
    assert record["event_id"] == "evt_test_1"
    assert record["category"] == "spine.cognition.brain.perceive.start"
    assert record["execution_point"] == "brain.perceive.start"
    assert record["channel"] == "fact"
    assert record["payload"] == {"state_id": "s1"}
    assert record["causation_id"] is None
    assert record["prev_event_hash"] is None
    assert record["event_hash"] is None
    assert lines[0] == json.dumps(record, sort_keys=True)


def test_spine_file_sink_rejects_non_spine_payload(tmp_path: Path) -> None:
    """非 SpineEventPayload 直接上抛 TypeError（无静默兜底）。"""
    sink = SpineFileSink(run_dir=tmp_path)
    try:
        with pytest.raises(TypeError, match="SpineEventPayload"):
            sink(object(), _ref())
    finally:
        sink.close()
