"""插件 Manifest 的稳定公开门面。

业务插件继续仅从此处或 ``lca.harness.plugin_api`` 导入 ``@plugin`` 与 Manifest 类型。
"""

from __future__ import annotations

from lca.harness.plugin.context import (
    AuditedPluginContext,
    PluginContext,
    PluginEventBus,
    UndeclaredInteractionError,
)
from lca.harness.plugin.declaration import PluginCarrier, definition_from_plugin, plugin
from lca.harness.plugin.manifest import (
    EffectClass,
    PluginDefinition,
    PluginKind,
    PluginMetadata,
    PluginSetupFn,
    RawRelationEntry,
)

__all__ = [
    "AuditedPluginContext",
    "EffectClass",
    "PluginCarrier",
    "PluginContext",
    "PluginDefinition",
    "PluginEventBus",
    "PluginKind",
    "PluginMetadata",
    "PluginSetupFn",
    "RawRelationEntry",
    "UndeclaredInteractionError",
    "definition_from_plugin",
    "plugin",
]
