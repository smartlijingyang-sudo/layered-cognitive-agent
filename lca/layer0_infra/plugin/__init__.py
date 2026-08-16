"""Plugin runtime — self-contained plugin system for LCA.

Architecture (mirrors DSH vendor/ structure):

    kernel/    → 核心运行时 (types, EventBus, Context, Host, Lifecycle, Service)
    loader/    → 拓扑加载 (PluginEntry, Loader, BootedTree)
    include/   → Profile 组合 (YAML bundle + patch + 模块解析)

依赖方向: kernel ← loader ← include

Public API — 从子包按需导入:
    from lca.layer0_infra.plugin.kernel import PluginHost, PluginContext, ...
    from lca.layer0_infra.plugin.loader import Loader, PluginEntry, ...
    from lca.layer0_infra.plugin.include import ProfileLoader, ...
"""
