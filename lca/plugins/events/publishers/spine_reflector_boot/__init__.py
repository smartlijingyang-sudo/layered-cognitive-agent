"""spine_reflector_boot — ADR-0181 PR-6。

boot 维度 3 EP（新加，PR-6）：
- boot.profile.resolved / .plugin.fiber.spawned / .observability.assembled
"""

from lca.plugins.events.publishers.spine_reflector_boot.plugin import (
    ReflectorClass,
    emit_boot_observability_assembled,
    emit_boot_plugin_fiber_spawned,
    emit_boot_profile_resolved,
)

__all__ = [
    "ReflectorClass",
    "emit_boot_observability_assembled",
    "emit_boot_plugin_fiber_spawned",
    "emit_boot_profile_resolved",
]
