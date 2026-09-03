"""sink manifest（ADR-0180 @plugin 形式）。"""
from __future__ import annotations

from typing import Any

from lca.contracts.event import Category

_PLUGIN_ID = "spine_chain_sink"
_SUBSCRIBES: tuple[Category, ...] = (
    Category("spine.cognition.brain.perceive.start"),
)

plugin_spec: dict[str, Any] = {
    "id": _PLUGIN_ID,
    "provides": ("events.sink",),
    "requires": ("lca.events.mechanism",),
    "layer": "plugin",
    "kind": "events.sink",
    "effects": ("writes:spine_chain.jsonl",),
    "event_subscribes": _SUBSCRIBES,
    "test_suite": "tests.plugins.events.sinks.test_spine_chain_sink",
}

__all__ = ["plugin_spec"]
