"""spine_reflector_phase_graph publisher 端到端测试（ADR-0181 PR-5）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from lca_kernel.events.mechanism import EventMechanism
from lca_kernel.events.registry import EventRegistry


@pytest.fixture
def mechanism() -> EventMechanism:
    config_dir = Path(__file__).resolve().parents[4] / "lca_kernel" / "events" / "config"
    return EventMechanism(EventRegistry.load(config_dir))


def test_emit_phase_graph_all(mechanism: EventMechanism) -> None:
    from lca.plugins.events.publishers.spine_reflector_phase_graph import (
        plugin,
    )

    EventMechanism.set_default(mechanism)
    try:
        ref = plugin.emit_phase_graph_node_start(node_id="n1", run_id="r1")
        assert ref.category == "spine.phase_graph.node.start"
        ref = plugin.emit_phase_graph_node_end(node_id="n1", run_id="r1")
        assert ref.category == "spine.phase_graph.node.end"
        ref = plugin.emit_phase_graph_edge_transit(from_node="n1", to_node="n2", run_id="r1")
        assert ref.category == "spine.phase_graph.edge.transit"
        ref = plugin.emit_phase_graph_instrument_coverage(
            covered_nodes=8, total_nodes=10, run_id="r1"
        )
        assert ref.category == "spine.phase_graph.instrument.coverage"
    finally:
        EventMechanism.set_default(None)
