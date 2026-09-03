"""DelegationCachePlugin 包（ADR-0180 / plugin-universe PR-4）。

PR-4 折叠：原 ``manifest.py + plugin.py`` 双形态合并为单文件 ``@plugin`` 入口；
``__init__.py`` 仅 re-export ``setup`` 满足 ``@plugin`` 的 ``$module`` 路径解析
（lca.plugins.events.publishers.delegation_cache）。
"""
from lca.plugins.events.publishers.delegation_cache.plugin import (
    PUBLISHER_PLUGIN_ID,
    DelegationCachePlugin,
    setup,
)

__all__ = ["PUBLISHER_PLUGIN_ID", "DelegationCachePlugin", "setup"]
