"""spine_loop_cursor publisher 端到端测试（ADR-0181 PR-10）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from lca_kernel.events.mechanism import EventMechanism
from lca_kernel.events.registry import EventRegistry


@pytest.fixture
def mechanism() -> EventMechanism:
    config_dir = Path(__file__).resolve().parents[4] / "lca_kernel" / "events" / "config"
    return EventMechanism(EventRegistry.load(config_dir))


def test_loop_cursor_send(mechanism: EventMechanism) -> None:
    from lca.plugins.events.publishers.spine_loop_cursor.plugin import (
        LoopCursorPlugin,
    )

    EventMechanism.set_default(mechanism)
    try:
        ref = LoopCursorPlugin.send(
            execution_point="phase.think.fold",
            channel="fact",
            payload={"step": 1, "run_id": "r1"},
        )
        assert ref.category == "spine.phase.think.fold"
    finally:
        EventMechanism.set_default(None)
