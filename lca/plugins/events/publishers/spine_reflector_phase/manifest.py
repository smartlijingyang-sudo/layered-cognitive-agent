"""publisher manifest（ADR-0180 @plugin 形式）。"""
from __future__ import annotations

from typing import Any

from lca.contracts.event import Category

_PLUGIN_ID = "spine_reflector_phase"
_PUBLISHES: tuple[Category, ...] = (
    Category("spine.perceive.phase.fold"),
    Category("spine.phase.perceive.fold"),
    Category("spine.phase.think.fold"),
    Category("spine.phase.gate.fold"),
    Category("spine.phase.remember.fold"),
    Category("spine.phase.stop.fold"),
    Category("spine.phase.reflect.fold"),
    Category("spine.phase.act.fold.start"),
    Category("spine.phase.act.fold.end"),
    Category("spine.phase.act.fold"),
    Category("spine.phase.tool.call.start"),
    Category("spine.phase.tool.call.end"),
    Category("spine.phase.tool.denied"),
)

plugin_spec: dict[str, Any] = {
    "id": _PLUGIN_ID,
    "provides": ("events.publish",),
    "requires": ("lca.events.mechanism",),
    "layer": "plugin",
    "kind": "events.publisher",
    "effects": tuple(f"emits:{c.value}" for c in _PUBLISHES),
    "event_publishes": _PUBLISHES,
    "test_suite": "tests.plugins.events.publishers.test_spine_reflector_phase",
}

__all__ = ["plugin_spec"]
