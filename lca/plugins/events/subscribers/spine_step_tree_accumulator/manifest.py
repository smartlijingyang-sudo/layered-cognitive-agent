"""subscriber manifest（ADR-0180 @plugin 形式）。"""
from __future__ import annotations

from typing import Any

from lca.contracts.event import Category

_PLUGIN_ID = "spine_step_tree_accumulator"
_SUBSCRIBES: tuple[Category, ...] = (
    Category("spine.cognition.brain.perceive.start"),
)

plugin_spec: dict[str, Any] = {
    "id": _PLUGIN_ID,
    "provides": ("events.subscriber",),
    "requires": ("lca.events.mechanism",),
    "layer": "plugin",
    "kind": "events.subscriber",
    "effects": ("derives:step_tree",),
    "event_subscribes": _SUBSCRIBES,
    "test_suite": "tests.plugins.events.subscribers.test_spine_step_tree_accumulator",
}

__all__ = ["plugin_spec"]
