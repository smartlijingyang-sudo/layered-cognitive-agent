# COMPAT(owner: ADR-0194, from: lca.plugins.phase_graph.think,
# to: lca.plugins.loop.phase.think.standard.plugin, delete_when: rg "lca\.plugins\.phase_graph\.think"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.loop.phase.think.standard.plugin)
"""Legacy re-export shim."""
from lca.plugins.loop.phase.think.standard.plugin import *  # noqa: F403
