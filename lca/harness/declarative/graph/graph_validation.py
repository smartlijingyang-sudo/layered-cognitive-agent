# COMPAT(owner: ADR-0194, from: lca.harness.declarative.graph.graph_validation,
# to: lca.harness.graph.graph_validation,
# delete_when: rg "from lca\\.harness\\.declarative\\.graph\\.graph_validation" 生产引用归零,
# forbidden_new_usage: 新代码优先 from lca.harness.graph.graph_validation import PhaseGraphValidator)
"""COMPAT re-export — see ``lca.harness.graph.graph_validation``."""

from lca.harness.graph.graph_validation import PhaseGraphValidator

__all__ = ["PhaseGraphValidator"]
