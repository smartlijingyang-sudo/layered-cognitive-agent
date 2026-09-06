# COMPAT(owner: ADR-0194, from: lca.harness.declarative.lifecycle.phase_transaction,
# to: lca.loop.transaction,
# delete_when: rg "from lca\\.harness\\.declarative\\.lifecycle\\.phase_transaction" 生产引用归零,
# forbidden_new_usage: 新代码优先 from lca.loop.transaction import PhaseExecutionTransaction)
"""COMPAT re-export — see ``lca.loop.transaction``."""

from lca.loop.transaction import PhaseExecutionTransaction, PhaseTransactionResult

__all__ = ["PhaseExecutionTransaction", "PhaseTransactionResult"]
