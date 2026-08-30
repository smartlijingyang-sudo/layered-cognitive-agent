"""Protocol contracts for independently selectable collaboration graph nodes.

The graph traversal kernel owns topology, readiness, and edge semantics.  Each
``GraphNodeExecutor`` owns the behavior for exactly one declared ``NodeType``.
This preserves the closed DAG invariants while making node behavior selectable
through a profile-provided registry.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from lca.contracts.models.core.result import Result
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.team.graph import ExecutionGraph, GraphNode, NodeType
from lca.contracts.protocols.infra import StateStore
from lca.contracts.protocols.orchestration import TeamStage


@dataclass(frozen=True, slots=True)
class GraphNodeExecutionContext:
    """The closed, read-only inputs made available to one graph-node primitive."""

    node: GraphNode
    graph: ExecutionGraph
    objective: str
    state: AgentState
    stage: TeamStage
    predecessor_results: Mapping[str, Result]
    state_store: StateStore | None


@runtime_checkable
class GraphNodeExecutor(Protocol):
    """Execute one concrete graph node without owning graph traversal."""

    node_type: NodeType
    is_aggregator: bool

    async def execute(self, context: GraphNodeExecutionContext) -> Result | None:
        """Return a node result, or ``None`` for a no-op topology node."""


@runtime_checkable
class GraphNodeExecutorRegistryProtocol(Protocol):
    """Resolve a node primitive by its closed ``NodeType`` vocabulary."""

    def register(self, node_type: NodeType, executor: GraphNodeExecutor) -> None:
        """Register exactly one executor for a node type."""

    def resolve(self, node_type: NodeType) -> GraphNodeExecutor:
        """Return the executor for a declared node type or fail closed."""


__all__ = [
    "GraphNodeExecutionContext",
    "GraphNodeExecutor",
    "GraphNodeExecutorRegistryProtocol",
]
