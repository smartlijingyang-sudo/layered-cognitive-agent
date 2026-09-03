"""publisher manifest（ADR-0180 @plugin 形式）。"""
from __future__ import annotations

from typing import Any

from lca.contracts.event import Category

_PLUGIN_ID = "spine_reflector_agent_spawn"
_PUBLISHES: tuple[Category, ...] = (
    Category("spine.agent_loop.iteration.start"),
    Category("spine.agent_loop.iteration.end"),
    Category("spine.agent.spawn"),
    Category("spine.agent.iteration"),
    Category("spine.agent.final"),
)

plugin_spec: dict[str, Any] = {
    "id": _PLUGIN_ID,
    "provides": ("events.publish",),
    "requires": ("lca.events.mechanism",),
    "layer": "plugin",
    "kind": "events.publisher",
    "effects": tuple(f"emits:{c.value}" for c in _PUBLISHES),
    "event_publishes": _PUBLISHES,
    "test_suite": "tests.plugins.events.publishers.test_spine_reflector_agent_spawn",
}

__all__ = ["plugin_spec"]
