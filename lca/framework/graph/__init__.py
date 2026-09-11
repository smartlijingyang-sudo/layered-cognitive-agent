"""Unified graph kernel — single visit state machine, one strategy per binding.

PR-3 lays the skeleton: a strategy registry, three strategies that
delegate to host-injected closures (typically
:class:`lca.loop.transaction.PhaseExecutionTransaction` for phase
nodes), and a ``PhaseExecutorLookup`` seam the strategies call to
resolve an executor from a ``(binding, node_id)`` pair.

PR-4 adds the kernel itself: :class:`PlanInterpreter` is the single
visit state machine, :class:`PlanTraversal` is the typed cursor,
:class:`PortRegistry` is the typed port store, :func:`lift_graph_spec`
and :func:`lift_executable_plan` are the yaml/DTO lifters, and
:class:`VisitRecorder` is the trace SSOT.

Subsequent PRs:

- PR-5: ``transform`` / ``observe`` / ``terminate`` / ``parallel``
  / ``gate_chain`` strategies.
- PR-6: ``agent_consult`` / ``agent_fanout`` strategies +
  ``AgentClient`` port.
- PR-7 (factory cutover): production interpreter returns
  ``PlanInterpreterAdapter``.
- Act-subgraph seam cutover (note 2026-09-11): deletes the legacy
  ``lca/framework/declarative/`` and ``lca/framework/subgraph/``
  directories; ``PlanInterpreterAdapter`` is the sole production entry
  point.
"""
from lca.framework.graph.adapter import PlanInterpreterAdapter
from lca.framework.graph.interpreter import InterpretationResult, PlanInterpreter
from lca.framework.graph.lifter import (
    lift_executable_plan,
    lift_graph_spec,
)
from lca.framework.graph.port_registry import PortRegistry
from lca.framework.graph.recorder import VisitRecorder
from lca.framework.graph.strategy_registry import (
    PhaseExecutorLookup,
    StrategyRegistry,
    default_strategy_registry,
    register_strategy,
    resolve_executor,
)
from lca.framework.graph.traversal import (
    PlanTraversal,
    install_predicate_evaluator,
    select_edge,
)

__all__ = [
    "InterpretationResult",
    "PhaseExecutorLookup",
    "PlanInterpreter",
    "PlanInterpreterAdapter",
    "PlanTraversal",
    "PortRegistry",
    "StrategyRegistry",
    "VisitRecorder",
    "default_strategy_registry",
    "install_predicate_evaluator",
    "lift_executable_plan",
    "lift_graph_spec",
    "register_strategy",
    "resolve_executor",
    "select_edge",
]
