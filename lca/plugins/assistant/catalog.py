# COMPAT(owner: ADR-0195, from: lca.plugins.assistant.catalog,
# to: lca.plugins.domain.assistant.catalog.plugin, delete_when: rg "lca\.plugins\.assistant\.catalog"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.domain.assistant.catalog.plugin)
"""Legacy re-export shim."""
from lca.plugins.domain.assistant.catalog.plugin import *  # noqa: F403
