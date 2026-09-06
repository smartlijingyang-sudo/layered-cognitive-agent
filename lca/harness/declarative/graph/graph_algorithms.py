# COMPAT(owner: ADR-0194, from: lca.harness.declarative.graph.graph_algorithms,
# to: lca.harness.graph.graph_algorithms,
# delete_when: rg "from lca\\.harness\\.declarative\\.graph\\.graph_algorithms" 生产引用归零,
# forbidden_new_usage: 新代码优先 from lca.harness.graph.graph_algorithms import ...)
"""COMPAT re-export — see ``lca.harness.graph.graph_algorithms``."""

from lca.harness.graph.graph_algorithms import (
    has_directed_cycle,
    has_path_between_any,
    reachable,
    strongly_connected_components,
)

__all__ = [
    "has_directed_cycle",
    "has_path_between_any",
    "reachable",
    "strongly_connected_components",
]
