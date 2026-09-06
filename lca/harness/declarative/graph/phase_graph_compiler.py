# COMPAT(owner: ADR-0194, from: lca.harness.declarative.graph.phase_graph_compiler,
# to: lca.harness.graph.phase_graph_compiler,
# delete_when: rg "from lca\\.harness\\.declarative\\.graph\\.phase_graph_compiler" 生产引用归零,
# forbidden_new_usage: 新代码优先 from lca.harness.graph.phase_graph_compiler import ...)
"""COMPAT re-export — see ``lca.harness.graph.phase_graph_compiler``."""

from lca.harness.graph.phase_graph_compiler import (
    PhaseGraphProjection,
    compile_phase_graph_projection,
)

__all__ = ["PhaseGraphProjection", "compile_phase_graph_projection"]
