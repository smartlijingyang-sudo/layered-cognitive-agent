"""publisher manifest（ADR-0180 @plugin 形式）。"""
from __future__ import annotations

from lca.contracts.event import Category
from lca_kernel.events.payloads import EventPluginSpec

# publisher plugin id 字符串：spine_reflector_cognition（与 yaml publishers 同名）
# 鉴权：PluginSpec.event_publishes ⊆ yaml publishers 白名单。
_PLUGIN_ID = "spine_reflector_cognition"
_PUBLISHES: tuple[Category, ...] = (
    Category("spine.cognition.brain.perceive.start"),
)

# Typed 鉴权声明（ADR-0180 D3，EventBus 鉴权矩阵接收）。
# plugin_id 必须是 plugin class 全路径，与 yaml publishers 解析后 class 一致。
event_plugin_spec = EventPluginSpec(
    plugin_id="lca.plugins.events.publishers.spine_reflector_cognition.plugin.ReflectorClass",
    event_publishes=frozenset(_PUBLISHES),
)

# 旧 `plugin_spec: dict[str, Any]` 形态保留为参考；机制不读，doc/test 用。
plugin_spec: dict[str, object] = {
    "id": _PLUGIN_ID,
    "provides": ("events.publish",),
    "requires": ("lca.events.mechanism",),
    "layer": "plugin",
    "kind": "events.publisher",
    "effects": ("emits:spine.cognition.brain.perceive.start",),
    "event_publishes": _PUBLISHES,
    "test_suite": "tests.plugins.events.publishers.test_spine_reflector_cognition",
}

__all__ = ["event_plugin_spec", "plugin_spec"]
