"""subscriber manifest（ADR-0180 @plugin 形式）。"""
from __future__ import annotations

from lca.contracts.event import Category
from lca_kernel.events.payloads import EventPluginSpec

_PLUGIN_ID = "spine_step_tree_accumulator"
_SUBSCRIBES: tuple[Category, ...] = (
    Category("spine.cognition.brain.perceive.start"),
)

event_plugin_spec = EventPluginSpec(
    plugin_id="lca.plugins.events.subscribers.spine_step_tree_accumulator.subscriber.SpineStepTreeAccumulator",
    event_subscribes=frozenset(_SUBSCRIBES),
)

plugin_spec: dict[str, object] = {
    "id": _PLUGIN_ID,
    "provides": ("events.subscriber",),
    "requires": ("lca.events.mechanism",),
    "layer": "plugin",
    "kind": "events.subscriber",
    "effects": ("derives:step_tree",),
    "event_subscribes": _SUBSCRIBES,
    "test_suite": "tests.plugins.events.subscribers.test_spine_step_tree_accumulator",
}

__all__ = ["event_plugin_spec", "plugin_spec"]
