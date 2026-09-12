"""BindingKind — closed set of graph node kinds the kernel dispatches to.

Adding a new graph-level orchestration primitive (e.g. an agent-team
fan-in node) means adding a new entry here, writing one strategy
class in :mod:`lca.framework.graph.strategies`, and registering it in
the strategy registry. Nothing else.

Each entry maps 1:1 to one :class:`lca.contracts.protocols.graph.strategy.NodeStrategy`
implementation. The kernel dispatches via :func:`lca.framework.graph.strategy_registry.strategy_for`.
"""
from __future__ import annotations

from enum import Enum


class BindingKind(str, Enum):
    """Closed enumeration of graph node kinds.

    The string value is the canonical name; yaml ``binding:`` fields
    deserialize via :class:`lca.framework.graph.lifter.PlanLifter`. Adding
    a value here requires a matching strategy implementation and an
    entry in the strategy registry — neither will silently default.
    """

    NODE_EXECUTOR = "node_executor"
    SUBGRAPH = "subgraph"
    AGENT_CONSULT = "agent_consult"
    AGENT_FANOUT = "agent_fanout"
    GATE_CHAIN = "gate_chain"
    TRANSFORM = "transform"
    PARALLEL = "parallel"
    OBSERVE = "observe"
    TERMINATE = "terminate"


__all__ = ["BindingKind"]