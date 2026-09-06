# COMPAT(owner: ADR-0195, from: lca.plugins.brain._standard_factory,
# to: lca.plugins.cognitive.brain._standard_factory, delete_when: rg "lca\.plugins\.brain\._standard_factory"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.cognitive.brain._standard_factory)
"""Legacy re-export shim."""
from lca.plugins.cognitive.brain._standard_factory import *  # noqa: F403
