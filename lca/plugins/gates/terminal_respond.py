# COMPAT(owner: ADR-0195, from: lca.plugins.gates.terminal_respond,
# to: lca.plugins.cognitive.gate.terminal_respond.plugin, delete_when: rg "lca\.plugins\.gates\.terminal_respond"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.cognitive.gate.terminal_respond.plugin)
"""Legacy re-export shim."""
from lca.plugins.cognitive.gate.terminal_respond.plugin import *  # noqa: F403
