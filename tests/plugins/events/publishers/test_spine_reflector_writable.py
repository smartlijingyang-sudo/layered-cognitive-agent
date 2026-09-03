"""spine_reflector_writable publisher 端到端测试（ADR-0181 PR-5）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from lca_kernel.events.bus import EventBus


@pytest.fixture
def bus() -> EventBus:
    config_dir = Path(__file__).resolve().parents[4] / "lca_kernel" / "events" / "config"
    from lca_kernel.events.test_catalog import build_test_bus
    return build_test_bus(config_dir)


def test_emit_writable_all(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_reflector_writable import (
        plugin,
    )

    EventBus.set_default(bus)
    try:
        ref = plugin.emit_writable_step_start(step=1, run_id="r1")
        assert ref.category == "spine.writable.step.start"
        ref = plugin.emit_writable_step_end(step=1, run_id="r1")
        assert ref.category == "spine.writable.step.end"
        ref = plugin.emit_writable_segment_start(segment=0, step=1, run_id="r1")
        assert ref.category == "spine.writable.segment.start"
        ref = plugin.emit_writable_segment_end(segment=0, step=1, run_id="r1")
        assert ref.category == "spine.writable.segment.end"
        ref = plugin.emit_writable_iteration_halt(run_id="r1", reason="cancel")
        assert ref.category == "spine.writable.iteration.halt"
        ref = plugin.emit_writable_iteration_closing(run_id="r1")
        assert ref.category == "spine.writable.iteration.closing"
        ref = plugin.emit_writable_iteration_close(run_id="r1")
        assert ref.category == "spine.writable.iteration.close"
    finally:
        EventBus.set_default(None)
