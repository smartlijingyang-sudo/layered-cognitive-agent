# COMPAT(owner: ADR-0194, from: lca.plugins.control_contributions.think_guard,
# to: lca.plugins.loop.control.think_guard.plugin, delete_when: rg "lca\.plugins\.control_contributions\.think_guard"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.loop.control.think_guard.plugin)
"""Legacy re-export shim."""
from lca.plugins.loop.control.think_guard.plugin import *  # noqa: F403
