"""Unified graph kernel — single visit state machine, one strategy per binding.

PR-3 lays the skeleton: a strategy registry, three strategies that
delegate to the existing :class:`lca.loop.transaction.PhaseExecutionTransaction`
or :class:`lca.framework.subgraph.plugins.runner.SubgraphRunner` paths,
and a ``PhaseExecutorLookup`` seam the strategies call to resolve an
executor from a ``(binding, node_id)`` pair. Nothing in
``GenericPlanInterpreter`` or ``NodeGraphDriver`` changes in this PR —
the new kernel runs in parallel and is opt-in.

Future PRs:

- PR-4: :class:`PlanInterpreter` + :class:`PlanTraversal` (single visit
  state machine).
- PR-5: add ``transform`` / ``observe`` / ``terminate`` / ``parallel``
  / ``gate_chain`` strategies.
- PR-6: add ``agent_consult`` / ``agent_fanout`` strategies +
  ``AgentClient`` port.
- PR-7: delete the parallel interpreter / driver / runner stack.
"""
from lca.framework.graph.strategy_registry import (
    PhaseExecutorLookup,
    StrategyRegistry,
    default_strategy_registry,
    register_strategy,
    resolve_executor,
)

__all__ = [
    "PhaseExecutorLookup",
    "StrategyRegistry",
    "default_strategy_registry",
    "register_strategy",
    "resolve_executor",
]