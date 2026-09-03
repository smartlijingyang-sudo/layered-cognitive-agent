"""spine_loop_cursor publisher 端到端测试（ADR-0181 PR-10）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from lca_kernel.events.bus import EventBus
from lca_kernel.events.registry import EventRegistry


@pytest.fixture
def bus() -> EventBus:
    config_dir = Path(__file__).resolve().parents[4] / "lca_kernel" / "events" / "config"
    return EventBus(EventRegistry.load(config_dir))


def test_loop_cursor_send(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_loop_cursor.plugin import (
        LoopCursorPlugin,
    )

    EventBus.set_default(bus)
    try:
        ref = LoopCursorPlugin.send(
            execution_point="phase.think.fold",
            channel="fact",
            payload={"step": 1, "run_id": "r1"},
        )
        assert ref.category == "spine.phase.think.fold"
    finally:
        EventBus.set_default(None)
