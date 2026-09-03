"""publisher manifest（ADR-0180 @plugin 形式）。"""
from __future__ import annotations

from typing import Any

from lca.contracts.event import Category

# publisher plugin id 字符串：spine_reflector_body_llm（与 yaml publishers 同名）
_PLUGIN_ID = "spine_reflector_body_llm"
_PUBLISHES: tuple[Category, ...] = (
    Category("spine.body.tool.execute.start"),
    Category("spine.body.tool.execute.end"),
    Category("spine.body.tool.retry"),
    Category("spine.body.sandbox.enter"),
    Category("spine.body.sandbox.exit"),
    Category("spine.llm.call.start"),
    Category("spine.llm.call.end"),
    Category("spine.llm.stream.token"),
    Category("spine.llm.stream.stall"),
)

plugin_spec: dict[str, Any] = {
    "id": _PLUGIN_ID,
    "provides": ("events.publish",),
    "requires": ("lca.events.mechanism",),
    "layer": "plugin",
    "kind": "events.publisher",
    "effects": tuple(f"emits:{c.value}" for c in _PUBLISHES),
    "event_publishes": _PUBLISHES,
    "test_suite": "tests.plugins.events.publishers.test_spine_reflector_body_llm",
}

__all__ = ["plugin_spec"]
