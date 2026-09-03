"""publisher manifest（ADR-0180 @plugin 形式）。"""
from __future__ import annotations

from typing import Any

from lca.contracts.event import Category

# publisher plugin id 字符串：spine_reflector_cognition（与 yaml publishers 同名）
# 鉴权：PluginSpec.event_publishes ⊆ yaml publishers 白名单。
_PLUGIN_ID = "spine_reflector_cognition"
_PUBLISHES: tuple[Category, ...] = (
    Category("spine.cognition.brain.perceive.start"),
)

# PluginSpec 形式（动态，yaml 互校验时由 EventMechanism 拉取）。
plugin_spec: dict[str, Any] = {
    "id": _PLUGIN_ID,
    "provides": ("events.publish",),
    "requires": ("lca.events.mechanism",),
    "layer": "plugin",
    "kind": "events.publisher",
    "effects": ("emits:spine.cognition.brain.perceive.start",),
    "event_publishes": _PUBLISHES,
    "test_suite": "tests.plugins.events.publishers.test_spine_reflector_cognition",
}

__all__ = ["plugin_spec"]
