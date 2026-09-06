# COMPAT(owner: ADR-0194, from: lca.plugins.control_contributions.stop_focus,
# to: lca.plugins.loop.control.stop_focus.plugin, delete_when: rg "lca\.plugins\.control_contributions\.stop_focus"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.loop.control.stop_focus.plugin)
"""Legacy re-export shim."""
from lca.plugins.loop.control.stop_focus.plugin import *  # noqa: F403
