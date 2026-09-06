# COMPAT(owner: ADR-0195, from: lca.plugins.brain.modular,
# to: lca.plugins.cognitive.brain.modular, delete_when: rg "lca\.plugins\.brain\.modular"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.cognitive.brain.modular)
"""Legacy re-export shim."""
from lca.plugins.cognitive.brain.modular import *  # noqa: F403
