# COMPAT(owner: ADR-0195, from: lca.plugins.gates.tool_loop_breaker,
# to: lca.plugins.cognitive.gate.tool_loop_breaker.plugin, delete_when: rg "lca\.plugins\.gates\.tool_loop_breaker"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.cognitive.gate.tool_loop_breaker.plugin)
"""Legacy re-export shim."""
from lca.plugins.cognitive.gate.tool_loop_breaker.plugin import *  # noqa: F403
