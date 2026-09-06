# COMPAT(owner: ADR-0195, from: lca.plugins.body.safe_executor,
# to: lca.plugins.cognitive.body.safe_executor, delete_when: rg "lca\.plugins\.body\.safe_executor"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.cognitive.body.safe_executor)
"""Legacy re-export shim."""
from lca.plugins.cognitive.body.safe_executor import *  # noqa: F403
