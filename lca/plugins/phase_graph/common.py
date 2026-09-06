# COMPAT(owner: ADR-0194, from: lca.plugins.phase_graph.common,
# to: lca.plugins.loop.phase._shared.common, delete_when: rg "lca\.plugins\.phase_graph\.common"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.loop.phase._shared.common)
"""Legacy re-export shim."""
from lca.plugins.loop.phase._shared.common import *  # noqa: F403
