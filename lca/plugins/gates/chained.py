# COMPAT(owner: ADR-0195, from: lca.plugins.gates.chained,
# to: lca.plugins.cognitive.gate.chained.plugin, delete_when: rg "lca\.plugins\.gates\.chained"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.cognitive.gate.chained.plugin)
"""Legacy re-export shim."""
from lca.plugins.cognitive.gate.chained.plugin import *  # noqa: F403
