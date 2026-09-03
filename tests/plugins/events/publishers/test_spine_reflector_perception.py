"""spine_reflector_perception publisher 端到端测试（ADR-0181 PR-6）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from lca_kernel.events.bus import EventBus
from lca_kernel.events.registry import EventRegistry


@pytest.fixture
def bus() -> EventBus:
    config_dir = Path(__file__).resolve().parents[4] / "lca_kernel" / "events" / "config"
    return EventBus(EventRegistry.load(config_dir))


def test_emit_perception_all(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_reflector_perception import (
        plugin,
    )

    EventBus.set_default(bus)
    try:
        ref = plugin.emit_perception_observe(run_id="r1", source="s1")
        assert ref.category == "spine.perception.observe"
        ref = plugin.emit_attention_focus(run_id="r1", target="t1")
        assert ref.category == "spine.perception.attention.focus"
        ref = plugin.emit_attention_blur(run_id="r1", target="t1")
        assert ref.category == "spine.perception.attention.blur"
        ref = plugin.emit_perception_signal_detected(run_id="r1", signal_kind="k", score=0.9)
        assert ref.category == "spine.perception.signal.detected"
        ref = plugin.emit_perception_fused(run_id="r1", artifact_id="a1", sources=["s1"])
        assert ref.category == "spine.perception.fused"
        ref = plugin.emit_perception_artifact_built(run_id="r1", artifact_id="a1", size_bytes=1024)
        assert ref.category == "spine.perception.artifact.built"
    finally:
        EventBus.set_default(None)
