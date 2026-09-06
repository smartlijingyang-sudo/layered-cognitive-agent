# COMPAT(owner: ADR-0194, from: lca.plugins.phase_graph.capabilities,
# to: lca.plugins.loop.phase._shared.capabilities, delete_when: rg "lca\.plugins\.phase_graph\.capabilities"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.loop.phase._shared.capabilities)
"""Legacy re-export shim."""
from lca.plugins.loop.phase._shared.capabilities import *  # noqa: F403
