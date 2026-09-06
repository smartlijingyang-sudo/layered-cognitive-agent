# COMPAT(owner: ADR-0195, from: lca.plugins.assistant.tools,
# to: lca.plugins.domain.tools.assistant_tools.plugin, delete_when: rg "lca\.plugins\.assistant\.tools"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.domain.tools.assistant_tools.plugin)
"""Legacy re-export shim."""
from lca.plugins.domain.tools.assistant_tools.plugin import *  # noqa: F403
