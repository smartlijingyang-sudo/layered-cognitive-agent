# COMPAT(owner: ADR-0195, from: lca.plugins.gates.repeat_tool_call,
# to: lca.plugins.cognitive.gate.repeat_tool_call.plugin, delete_when: rg "lca\.plugins\.gates\.repeat_tool_call"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.cognitive.gate.repeat_tool_call.plugin)
"""Legacy re-export shim."""
from lca.plugins.cognitive.gate.repeat_tool_call.plugin import *  # noqa: F403
