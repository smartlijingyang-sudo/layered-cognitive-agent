"""Unified graph kernel — single visit state machine, one strategy per binding.

PR-3 lays the skeleton: a strategy registry and strategies that
delegate to host-injected closures (typically
``lca.plugins.composer.runtime.runtime.factory`` for node executors).

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
- Six-phase subgraph cutover (note 2026-09-12): every phase main
  binds ``subgraph`` / ``node_executor``; the framework never sees
  ``PhaseExecutor`` / ``PhaseInput`` / ``PhaseResult``.
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
    NodeExecutorLookup,
    StrategyRegistry,
    default_strategy_registry,
    register_strategy,
    resolve_executor,
)
from lca.framework.graph.strategies import (  # noqa: F401  side-effect: register strategies
    agent_consult_strategy,
    agent_fanout_strategy,
    gate_chain_strategy,
    node_executor_strategy,
    observe_strategy,
    parallel_strategy,
    subgraph_strategy,
    terminate_strategy,
    transform_strategy,
)
from lca.framework.graph.traversal import (
    PlanTraversal,
    install_predicate_evaluator,
    select_edge,
)

__all__ = [
    "InterpretationResult",
    "NodeExecutorLookup",
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
