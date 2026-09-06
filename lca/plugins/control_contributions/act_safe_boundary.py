# COMPAT(owner: ADR-0194, from: lca.plugins.control_contributions.act_safe_boundary,
# to: lca.plugins.loop.control.act_safe_boundary.plugin, delete_when: rg "lca\.plugins\.control_contributions\.act_safe_boundary"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.loop.control.act_safe_boundary.plugin)
"""Legacy re-export shim."""
from lca.plugins.loop.control.act_safe_boundary.plugin import *  # noqa: F403
