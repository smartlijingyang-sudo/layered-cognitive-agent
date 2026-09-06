# COMPAT(owner: ADR-0194, from: lca.plugins.control_contributions.observe_checkpoint,
# to: lca.plugins.loop.control.observe_checkpoint.plugin, delete_when: rg "lca\.plugins\.control_contributions\.observe_checkpoint"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.loop.control.observe_checkpoint.plugin)
"""Legacy re-export shim."""
from lca.plugins.loop.control.observe_checkpoint.plugin import *  # noqa: F403
