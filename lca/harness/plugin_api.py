"""插件 Manifest 稳定公开门面 — 业务插件从此处导入 ``@plugin`` 与 Manifest 类型。"""

from lca.harness.plugin import (
    AuditedPluginContext,
    EffectClass,
    PluginCarrier,
    PluginContext,
    PluginDefinition,
    PluginEventBus,
    PluginKind,
    PluginMetadata,
    PluginSetupFn,
    RawRelationEntry,
    UndeclaredInteractionError,
    definition_from_plugin,
    plugin,
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
