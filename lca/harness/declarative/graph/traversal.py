# COMPAT(owner: ADR-0194, from: lca.harness.declarative.graph.traversal,
# to: lca.harness.graph.traversal,
# delete_when: rg "from lca\\.harness\\.declarative\\.graph\\.traversal" 生产引用归零,
# forbidden_new_usage: 新代码优先 from lca.harness.graph.traversal import PhaseTraversal)
"""COMPAT re-export — see ``lca.harness.graph.traversal``."""

from lca.harness.graph.traversal import PhaseTraversal

__all__ = ["PhaseTraversal"]
