# COMPAT(owner: ADR-0195, from: lca.plugins.loop_drivers.registry,
# to: lca.plugins.loop.driver.plugin, delete_when: rg "lca\.plugins\.loop_drivers\.registry"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.loop.driver.plugin)
"""Legacy re-export shim."""
from lca.plugins.loop.driver.plugin import (
    RunLoopDriverRegistry,
    _UnknownExecutionTargetError,
    plugin as loop_driver_plugin,
)

__all__ = [
    "RunLoopDriverRegistry",
    "_UnknownExecutionTargetError",
    "loop_driver_plugin",
]
