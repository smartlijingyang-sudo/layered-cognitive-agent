# COMPAT(owner: ADR-0195, from: lca.plugins.body.simple,
# to: lca.plugins.cognitive.body.simple, delete_when: rg "lca\.plugins\.body\.simple"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.cognitive.body.simple)
"""Legacy re-export shim."""
from lca.plugins.cognitive.body.simple import *  # noqa: F403
