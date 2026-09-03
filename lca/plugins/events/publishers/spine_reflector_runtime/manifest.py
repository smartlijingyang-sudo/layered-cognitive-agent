"""publisher manifest（ADR-0180 @plugin 形式）。"""
from __future__ import annotations

from lca.contracts.event import Category
from lca_kernel.events.payloads import EventPluginSpec

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

event_plugin_spec = EventPluginSpec(
    plugin_id="lca.plugins.events.publishers.spine_reflector_runtime.plugin.ReflectorClass",
    event_publishes=frozenset(_PUBLISHES),
)

plugin_spec: dict[str, object] = {
    "id": _PLUGIN_ID,
    "provides": ("events.publish",),
    "requires": ("lca.events.mechanism",),
    "layer": "plugin",
    "kind": "events.publisher",
    "effects": tuple(f"emits:{c.value}" for c in _PUBLISHES),
    "event_publishes": _PUBLISHES,
    "test_suite": "tests.plugins.events.publishers.test_spine_reflector_runtime",
}

__all__ = ["event_plugin_spec", "plugin_spec"]
