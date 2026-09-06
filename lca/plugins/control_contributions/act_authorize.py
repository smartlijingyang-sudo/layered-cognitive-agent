# COMPAT(owner: ADR-0194, from: lca.plugins.control_contributions.act_authorize,
# to: lca.plugins.loop.control.act_authorize.plugin, delete_when: rg "lca\.plugins\.control_contributions\.act_authorize"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.loop.control.act_authorize.plugin)
"""Legacy re-export shim."""
from lca.plugins.loop.control.act_authorize.plugin import *  # noqa: F403
