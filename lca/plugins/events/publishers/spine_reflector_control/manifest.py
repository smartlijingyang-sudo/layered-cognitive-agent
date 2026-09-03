"""publisher manifest（ADR-0180 @plugin 形式）。"""
from __future__ import annotations

from typing import Any

from lca.contracts.event import Category

_PLUGIN_ID = "spine_reflector_control"
_PUBLISHES: tuple[Category, ...] = (
    Category("spine.control.dispatch"),
    Category("spine.control.invoke"),
    Category("spine.control.signal"),
    Category("spine.control.approve.request"),
    Category("spine.control.approve.response"),
    Category("spine.control.deny"),
    Category("spine.control.revoke"),
    Category("spine.control.pause"),
    Category("spine.control.resume"),
    Category("spine.control.stop"),
    Category("spine.control.accept"),
)

plugin_spec: dict[str, Any] = {
    "id": _PLUGIN_ID,
    "provides": ("events.publish",),
    "requires": ("lca.events.mechanism",),
    "layer": "plugin",
    "kind": "events.publisher",
    "effects": tuple(f"emits:{c.value}" for c in _PUBLISHES),
    "event_publishes": _PUBLISHES,
    "test_suite": "tests.plugins.events.publishers.test_spine_reflector_control",
}

__all__ = ["plugin_spec"]
