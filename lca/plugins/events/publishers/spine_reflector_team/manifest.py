"""publisher manifest（ADR-0180 @plugin 形式）。"""
from __future__ import annotations

from typing import Any

from lca.contracts.event import Category

_PLUGIN_ID = "spine_reflector_team"
_PUBLISHES: tuple[Category, ...] = (
    Category("spine.team.casting.started"),
    Category("spine.team.casting.completed"),
    Category("spine.team.casting.failed"),
    Category("spine.team.delegation.issued"),
    Category("spine.team.delegation.completed"),
    Category("spine.team.delegation.cache_hit"),
    Category("spine.team.message.published"),
)

plugin_spec: dict[str, Any] = {
    "id": _PLUGIN_ID,
    "provides": ("events.publish",),
    "requires": ("lca.events.mechanism",),
    "layer": "plugin",
    "kind": "events.publisher",
    "effects": tuple(f"emits:{c.value}" for c in _PUBLISHES),
    "event_publishes": _PUBLISHES,
    "test_suite": "tests.plugins.events.publishers.test_spine_reflector_team",
}

__all__ = ["plugin_spec"]
