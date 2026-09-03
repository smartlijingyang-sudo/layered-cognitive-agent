"""spine_reflector_boot publisher 端到端测试（ADR-0181 PR-6）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from lca_kernel.events.bus import EventBus


@pytest.fixture
def bus() -> EventBus:
    config_dir = Path(__file__).resolve().parents[4] / "lca_kernel" / "events" / "config"
    from lca_kernel.events.test_catalog import build_test_bus
    return build_test_bus(config_dir)


def test_emit_boot_all(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_reflector_boot import (
        plugin,
    )

    EventBus.set_default(bus)
    try:
        ref = plugin.emit_boot_profile_resolved(profile="p", plugins=10)
        assert ref.category == "spine.boot.profile.resolved"
        ref = plugin.emit_boot_plugin_fiber_spawned(plugin_id="pid", layer="L0")
        assert ref.category == "spine.boot.plugin.fiber.spawned"
        ref = plugin.emit_boot_observability_assembled(sinks=3, derivers=2)
        assert ref.category == "spine.boot.observability.assembled"
    finally:
        EventBus.set_default(None)
