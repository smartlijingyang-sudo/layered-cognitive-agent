"""publisher manifest（ADR-0180 @plugin 形式）。"""
from __future__ import annotations

from typing import Any

from lca.contracts.event import Category

_PLUGIN_ID = "spine_reflector_writable"
_PUBLISHES: tuple[Category, ...] = (
    Category("spine.writable.step.start"),
    Category("spine.writable.step.end"),
    Category("spine.writable.segment.start"),
    Category("spine.writable.segment.end"),
    Category("spine.writable.iteration.halt"),
    Category("spine.writable.iteration.closing"),
    Category("spine.writable.iteration.close"),
)

plugin_spec: dict[str, Any] = {
    "id": _PLUGIN_ID,
    "provides": ("events.publish",),
    "requires": ("lca.events.mechanism",),
    "layer": "plugin",
    "kind": "events.publisher",
    "effects": tuple(f"emits:{c.value}" for c in _PUBLISHES),
    "event_publishes": _PUBLISHES,
    "test_suite": "tests.plugins.events.publishers.test_spine_reflector_writable",
}

__all__ = ["plugin_spec"]
