"""publisher manifest（ADR-0180 @plugin 形式）。"""
from __future__ import annotations

from typing import Any

from lca.contracts.event import Category

# publisher plugin id 字符串：spine_reflector_runtime（与 yaml publishers 同名）
_PLUGIN_ID = "spine_reflector_runtime"
_PUBLISHES: tuple[Category, ...] = (
    Category("spine.exception.caught"),
    Category("spine.exception.finally"),
    Category("spine.lifecycle.finally"),
    Category("spine.runtime.reducer.apply"),
    Category("spine.runtime.checkpoint.create"),
    Category("spine.runtime.resume.start"),
    Category("spine.runtime.resume.end"),
    Category("spine.runtime.event_publisher.publish"),
    Category("spine.runtime.observed"),
)

plugin_spec: dict[str, Any] = {
    "id": _PLUGIN_ID,
    "provides": ("events.publish",),
    "requires": ("lca.events.mechanism",),
    "layer": "plugin",
    "kind": "events.publisher",
    "effects": tuple(f"emits:{c.value}" for c in _PUBLISHES),
    "event_publishes": _PUBLISHES,
    "test_suite": "tests.plugins.events.publishers.test_spine_reflector_runtime",
}

__all__ = ["plugin_spec"]
