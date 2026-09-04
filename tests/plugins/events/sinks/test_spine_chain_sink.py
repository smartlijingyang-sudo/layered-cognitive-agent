"""spine_chain_sink 端到端（ADR-0181 试点盖章条件 5: chain 完整性 / ADR-0183 PR-7）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.contracts.event import Category
from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
    ReflectorClass,
)
from lca.plugins.events.sinks.spine_chain_sink.sink import SpineChainSink
from lca_kernel.events.bus import EventBus
from lca_kernel.events.hooks import FailureSemantics
from lca_kernel.events.payloads import SpineEventPayload


@pytest.fixture
def bus(tmp_path) -> EventBus:
    """独立 EventBus 实例,sink 直接挂在它上面。"""
    config_dir = Path(__file__).resolve().parents[4] / "lca_kernel" / "events" / "config"
    from lca_kernel.events.test_catalog import build_test_bus

    b = build_test_bus(config_dir)
    sink = SpineChainSink(output_path=tmp_path / "chain.jsonl")
    b.subscribe(
        plugin=SpineChainSink,
        category=Category("spine.cognition.brain.perceive.start"),
        on_event=sink,
        failure=FailureSemantics.FAIL_FAST,
    )
    return b


def test_chain_sink_writes_two_records_with_hashes(bus: EventBus, tmp_path: Path) -> None:
    """盖章 5: sink 落盘时算 hash chain,2 个 record 形成 prev_event_hash 链。"""
    chain_path = tmp_path / "chain.jsonl"
    assert not chain_path.exists()

    bus.publish(
        SpineEventPayload(
            execution_point="brain.perceive.start",
            channel="fact",
            payload={"state_id": "s1"},
        ),
        producer=ReflectorClass,
    )
    bus.publish(
        SpineEventPayload(
            execution_point="brain.perceive.start",
            channel="fact",
            payload={"state_id": "s2"},
        ),
        producer=ReflectorClass,
    )

    assert chain_path.exists()
    records = [json.loads(line) for line in chain_path.read_text().splitlines() if line]
    assert len(records) == 2
    assert records[0]["prev_event_hash"] is None
    assert records[0]["event_hash"] is not None
    assert records[1]["prev_event_hash"] == records[0]["event_hash"]
    assert records[1]["event_hash"] != records[0]["event_hash"]
