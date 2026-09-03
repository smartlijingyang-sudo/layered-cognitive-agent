"""publisher manifest（ADR-0180 @plugin 形式）。"""
from __future__ import annotations

from typing import Any

from lca.contracts.event import Category

_PLUGIN_ID = "spine_loop_cursor"
_PUBLISHES: tuple[Category, ...] = (
    Category("spine.phase.perceive.fold"),
    Category("spine.phase.think.fold"),
    Category("spine.phase.gate.fold"),
    Category("spine.phase.remember.fold"),
    Category("spine.phase.stop.fold"),
    Category("spine.phase.reflect.fold"),
    Category("spine.phase.act.fold"),
    Category("spine.writable.iteration.halt"),
    Category("spine.writable.iteration.closing"),
    Category("spine.writable.iteration.close"),
    Category("spine.step.thinking.record"),
    Category("spine.step.tool_call.record"),
    Category("spine.step.tool_result.record"),
    Category("spine.step.reflect.record"),
    Category("spine.step.span.record"),
)

plugin_spec: dict[str, Any] = {
    "id": _PLUGIN_ID,
    "provides": ("events.publish",),
    "requires": ("lca.events.mechanism",),
    "layer": "plugin",
    "kind": "events.publisher",
    "effects": tuple(f"emits:{c.value}" for c in _PUBLISHES),
    "event_publishes": _PUBLISHES,
    "test_suite": "tests.plugins.events.publishers.test_spine_loop_cursor",
}

__all__ = ["plugin_spec"]
