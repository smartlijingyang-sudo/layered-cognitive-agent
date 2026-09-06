# COMPAT(owner: ADR-0195, from: lca.plugins.gates.service,
# to: lca.plugins.cognitive.gate.service.plugin, delete_when: rg "lca\.plugins\.gates\.service"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.cognitive.gate.service.plugin)
"""Legacy re-export shim."""
from lca.plugins.cognitive.gate.service.plugin import *  # noqa: F403
