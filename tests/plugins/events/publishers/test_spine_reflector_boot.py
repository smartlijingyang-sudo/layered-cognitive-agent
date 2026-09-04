"""spine_reflector_boot publisher 端到端测试（ADR-0181 PR-6）。"""

from __future__ import annotations

from typing import Any


def test_emit_boot_all(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_reflector_boot import (
        plugin,
    )

    ref = plugin.emit_boot_profile_resolved(profile="p", plugins=10)
    assert ref.category == "spine.boot.profile.resolved"
    ref = plugin.emit_boot_plugin_fiber_spawned(plugin_id="pid", layer="L0")
    assert ref.category == "spine.boot.plugin.fiber.spawned"
    ref = plugin.emit_boot_observability_assembled(sinks=3, derivers=2)
    assert ref.category == "spine.boot.observability.assembled"
