"""sink manifest（ADR-0180 @plugin 形式）。"""
from __future__ import annotations

from lca.contracts.event import Category
from lca_kernel.events.payloads import EventPluginSpec

_PLUGIN_ID = "spine_chain_sink"
_SUBSCRIBES: tuple[Category, ...] = (
    Category("spine.cognition.brain.perceive.start"),
)

event_plugin_spec = EventPluginSpec(
    plugin_id="lca.plugins.events.sinks.spine_chain_sink.sink.SpineChainSink",
    event_subscribes=frozenset(_SUBSCRIBES),
)

plugin_spec: dict[str, object] = {
    "id": _PLUGIN_ID,
    "provides": ("events.sink",),
    "requires": ("lca.events.mechanism",),
    "layer": "plugin",
    "kind": "events.sink",
    "effects": ("writes:spine_chain.jsonl",),
    "event_subscribes": _SUBSCRIBES,
    "test_suite": "tests.plugins.events.sinks.test_spine_chain_sink",
}

__all__ = ["event_plugin_spec", "plugin_spec"]
