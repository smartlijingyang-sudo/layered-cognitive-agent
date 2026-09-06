# COMPAT(owner: ADR-0194, from: lca.plugins.control_contributions.remember_admit,
# to: lca.plugins.loop.control.remember_admit.plugin, delete_when: rg "lca\.plugins\.control_contributions\.remember_admit"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.loop.control.remember_admit.plugin)
"""Legacy re-export shim."""
from lca.plugins.loop.control.remember_admit.plugin import *  # noqa: F403
