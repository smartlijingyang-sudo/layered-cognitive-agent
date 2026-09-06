# COMPAT(owner: ADR-0194, from: lca.plugins.control_contributions.observe_wildcard,
# to: lca.plugins.loop.control.observe_wildcard.plugin, delete_when: rg "lca\.plugins\.control_contributions\.observe_wildcard"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.loop.control.observe_wildcard.plugin)
"""Legacy re-export shim."""
from lca.plugins.loop.control.observe_wildcard.plugin import *  # noqa: F403
