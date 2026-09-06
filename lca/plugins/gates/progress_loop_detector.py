# COMPAT(owner: ADR-0195, from: lca.plugins.gates.progress_loop_detector,
# to: lca.plugins.cognitive.gate.progress_loop_detector.plugin, delete_when: rg "lca\.plugins\.gates\.progress_loop_detector"
#   生产引用归零(bundles 除外), forbidden_new_usage: 新代码 import lca.plugins.cognitive.gate.progress_loop_detector.plugin)
"""Legacy re-export shim."""
from lca.plugins.cognitive.gate.progress_loop_detector.plugin import *  # noqa: F403
