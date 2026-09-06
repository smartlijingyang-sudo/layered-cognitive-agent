# COMPAT(owner: ADR-0194, from: lca.harness.declarative.graph.predicate,
# to: lca.harness.graph.predicate,
# delete_when: rg "from lca\\.harness\\.declarative\\.graph\\.predicate" 生产引用归零,
# forbidden_new_usage: 新代码优先 from lca.harness.graph.predicate import evaluate_restricted_predicate)
"""COMPAT re-export — see ``lca.harness.graph.predicate``."""

from lca.harness.graph.predicate import evaluate_restricted_predicate

__all__ = ["evaluate_restricted_predicate"]
