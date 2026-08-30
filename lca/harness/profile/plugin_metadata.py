"""已解析插件元数据的统一读取 seam。

Profile 解析器需要从同一个声明入口读取旧版 ``setup.meta`` 与模块级
``setup.plugin_meta``。模块级声明始终覆盖 setup 声明；该优先级与
CapabilityPlan 及声明式计划编译保持一致。

这里不解释任何具体字段（例如 ``relations``、``scope``），只提供稳定的
元数据视图。可执行控制不从通用元数据读取，而由 ``PluginSpec.contributes``
直接表达并接受领域校验。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lca.harness.profile.resolve import ResolvedPlugin


def plugin_metadata(plugin: ResolvedPlugin) -> dict[str, object]:
    """合并插件的 setup 与模块级元数据，后者优先。

    仅接受映射值；不合规的旧式载体与缺失字段都等价于空元数据，以保持各
    计划解析器此前的兼容行为。返回新字典，使调用方不能修改原始声明。
    """
    definition = getattr(plugin, "definition", None)
    setup = getattr(definition, "setup", None)
    metadata: dict[str, object] = {}
    for attribute in ("meta", "plugin_meta"):
        candidate = getattr(setup, attribute, None)
        if isinstance(candidate, Mapping):
            metadata.update(candidate)
    return metadata


__all__ = ["plugin_metadata"]
