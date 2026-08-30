"""Registry seam for collaboration graph node primitives."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.capabilities import GRAPH_NODE_EXECUTORS
from lca.contracts.models.team.graph import NodeType
from lca.contracts.protocols.collaboration.graph_node_executor import (
    GraphNodeExecutor,
    GraphNodeExecutorRegistryProtocol,
)
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin


class Config(BaseModel):
    """The node-executor registry has no configuration."""

    model_config = {"extra": "forbid"}


class GraphNodeExecutorRegistry(GraphNodeExecutorRegistryProtocol):
    """Closed-vocabulary registry with one owner per graph node type."""

    def __init__(self) -> None:
        self._executors: dict[NodeType, GraphNodeExecutor] = {}

    def register(self, node_type: NodeType, executor: GraphNodeExecutor) -> None:
        """Register one executor and reject duplicate or mismatched ownership."""

        normalized = NodeType(node_type)
        if executor.node_type is not normalized:
            raise ValueError(
                "graph_node_executors: executor node_type must match its registry key "
                f"({normalized.value!r})"
            )
        if normalized in self._executors:
            raise KeyError(
                f"graph_node_executors: executor already registered for {normalized.value!r}"
            )
        self._executors[normalized] = executor

    def resolve(self, node_type: NodeType) -> GraphNodeExecutor:
        """Return a node executor or fail closed with the declared alternatives."""

        normalized = NodeType(node_type)
        try:
            return self._executors[normalized]
        except KeyError as exc:
            available = ", ".join(sorted(item.value for item in self._executors))
            raise KeyError(
                "graph_node_executors: no executor registered for "
                f"{normalized.value!r}; available: {available or '<none>'}"
            ) from exc

    def node_types(self) -> tuple[NodeType, ...]:
        """Expose registered node types for boot-time and substitution tests."""

        return tuple(self._executors)


@plugin(
    id="lca.graph-node-executor-registry",
    Config=Config,
    provides=[GRAPH_NODE_EXECUTORS.key],
    requires=[],
    implements=[GraphNodeExecutorRegistryProtocol],
    layer="L3",
    kind=PluginKind.SEAM,
    effects=EffectClass.NONE,
    description="Provide the closed registry for collaboration graph-node primitives.",
    test_suite="tests/test_graph_node_executors.py",
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide an empty registry for independent node primitive contributors."""

    del config
    ctx.provide(GRAPH_NODE_EXECUTORS.key, GraphNodeExecutorRegistry())


__all__ = ["Config", "GraphNodeExecutorRegistry", "setup"]
