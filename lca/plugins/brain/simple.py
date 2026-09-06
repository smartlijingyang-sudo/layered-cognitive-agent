# COMPAT(owner: ADR-0195, from: lca.plugins.brain.simple,
# to: lca.plugins.cognitive.brain.simple, delete_when: rg "lca\.plugins\.brain\.simple"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.cognitive.brain.simple)
"""Legacy re-export shim."""
from lca.plugins.cognitive.brain.simple import *  # noqa: F403
