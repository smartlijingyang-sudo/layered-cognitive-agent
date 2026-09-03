"""spine_chain_sink 端到端（ADR-0181 试点盖章条件 5: chain 完整性）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
    ReflectorClass,
)
from lca.plugins.events.sinks.spine_chain_sink.sink import SpineChainSink
from lca_kernel.events.mechanism import EventMechanism
from lca_kernel.events.payloads import SpineEventPayload
from lca_kernel.events.registry import EventRegistry


@pytest.fixture
def mechanism(tmp_path) -> EventMechanism:
    from pathlib import Path

    SpineChainSink.reset()
    config_dir = Path(__file__).resolve().parents[4] / "lca_kernel" / "events" / "config"
    m = EventMechanism(EventRegistry.load(config_dir))
    sink = SpineChainSink(output_path=tmp_path / "chain.jsonl")
    m.register_sink(
        plugin=SpineChainSink,
        category=__import__("lca.contracts.event", fromlist=["Category"]).Category(
            "spine.cognition.brain.perceive.start"
        ),
        callback=sink,
    )
    return m


def test_chain_sink_writes_two_records_with_hashes(
    mechanism: EventMechanism, tmp_path: Path
) -> None:
    """盖章 5: sink 落盘时算 hash chain，2 个 record 形成 prev_event_hash 链。"""
    chain_path = tmp_path / "chain.jsonl"
    assert not chain_path.exists()

    mechanism.send(
        SpineEventPayload(
            execution_point="brain.perceive.start",
            channel="fact",
            payload={"state_id": "s1"},
        ),
        plugin=ReflectorClass,
    )
    mechanism.send(
        SpineEventPayload(
            execution_point="brain.perceive.start",
            channel="fact",
            payload={"state_id": "s2"},
        ),
        plugin=ReflectorClass,
    )

    assert chain_path.exists()
    records = [json.loads(line) for line in chain_path.read_text().splitlines() if line]
    assert len(records) == 2
    assert records[0]["prev_event_hash"] is None
    assert records[0]["event_hash"] is not None
    assert records[1]["prev_event_hash"] == records[0]["event_hash"]
    assert records[1]["event_hash"] != records[0]["event_hash"]
