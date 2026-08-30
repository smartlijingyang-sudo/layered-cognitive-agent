"""插件 Manifest 的稳定公开门面。

业务插件继续仅从此处导入 ``@plugin`` 与相关 Manifest 类型。实现按变化轴分为三条
内部接缝：``plugin_manifest`` 承载不可变声明事实，``plugin_declaration`` 适配
装饰器与 Cordis 载体，``plugin_context`` 执行启动期交互审计。门面不含行为，确保
公开接口保持稳定而内部复杂度具有局部性。
"""

from __future__ import annotations

from lca.harness.plugin_context import (
    AuditedPluginContext,
    PluginContext,
    PluginEventBus,
    UndeclaredInteractionError,
)
from lca.harness.plugin_declaration import PluginCarrier, definition_from_plugin, plugin
from lca.harness.plugin_manifest import (
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
