# COMPAT(owner: ADR-0195, from: lca.plugins.gates.artifact_respond_injector,
# to: lca.plugins.cognitive.gate.artifact_respond_injector.plugin, delete_when: rg "lca\.plugins\.gates\.artifact_respond_injector"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.cognitive.gate.artifact_respond_injector.plugin)
"""Legacy re-export shim."""
from lca.plugins.cognitive.gate.artifact_respond_injector.plugin import *  # noqa: F403
