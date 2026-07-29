"""ExecutionGraph —— DAG 编排契约。

定义图执行的数据结构：GraphNode、GraphEdge、ExecutionGraph。
提供拓扑校验（防环检测）和拓扑排序能力。
GraphStrategy 基于此数据结构执行工作流。
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from lca.contracts.state import TypedState


class NodeType(str, Enum):
    ENTRY = "entry"
    EXIT = "exit"
    AGENT = "agent"
    ROUTER = "router"
    AGGREGATOR = "aggregator"


class EdgeType(str, Enum):
    FIXED = "fixed"
    CONDITIONAL = "conditional"
    PARALLEL = "parallel"


ConditionFn = Callable[[TypedState], bool]


class GraphValidationError(Exception):
    """图拓扑校验失败。"""


@dataclass
class GraphNode:
    id: str
    type: NodeType
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    source: str
    target: str
    type: EdgeType = EdgeType.FIXED
    condition: ConditionFn | None = None


@dataclass
class ExecutionGraph:
    """有向图工作流定义。

    提供节点/边管理、拓扑校验（防环检测）、拓扑排序。
    默认 allow_cycle=False，除非显式标记为 True。
    """

    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    allow_cycle: bool = False

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        self.edges.append(edge)

    def outgoing(self, node_id: str) -> list[GraphEdge]:
        return [e for e in self.edges if e.source == node_id]

    def incoming(self, node_id: str) -> list[GraphEdge]:
        return [e for e in self.edges if e.target == node_id]

    def validate(self) -> None:
        """校验图拓扑完整性。

        检查项：
        1. 必须有 entry 和 exit 节点
        2. 所有边的 source/target 必须引用已注册的节点
        3. 防环检测（除非 allow_cycle=True）
        """
        if not any(n.type == NodeType.ENTRY for n in self.nodes.values()):
            raise GraphValidationError("图必须有至少一个 entry 节点")
        if not any(n.type == NodeType.EXIT for n in self.nodes.values()):
            raise GraphValidationError("图必须有至少一个 exit 节点")

        for edge in self.edges:
            if edge.source not in self.nodes:
                raise GraphValidationError(f"边的 source 节点不存在: {edge.source!r}")
            if edge.target not in self.nodes:
                raise GraphValidationError(f"边的 target 节点不存在: {edge.target!r}")

        if not self.allow_cycle:
            self._check_acyclic()

    def _check_acyclic(self) -> None:
        """Kahn 算法防环检测。"""
        in_degree: dict[str, int] = dict.fromkeys(self.nodes, 0)
        for edge in self.edges:
            in_degree[edge.target] += 1

        queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
        visited_count = 0

        while queue:
            nid = queue.popleft()
            visited_count += 1
            for edge in self.edges:
                if edge.source == nid:
                    in_degree[edge.target] -= 1
                    if in_degree[edge.target] == 0:
                        queue.append(edge.target)

        if visited_count != len(self.nodes):
            raise GraphValidationError("图包含环，但 allow_cycle=False")

    def topological_order(self) -> list[str]:
        """Kahn 算法拓扑排序。若图有环则返回的列表长度 < 节点数。"""
        in_degree: dict[str, int] = dict.fromkeys(self.nodes, 0)
        for edge in self.edges:
            in_degree[edge.target] += 1

        queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
        result: list[str] = []

        while queue:
            nid = queue.popleft()
            result.append(nid)
            for edge in self.edges:
                if edge.source == nid:
                    in_degree[edge.target] -= 1
                    if in_degree[edge.target] == 0:
                        queue.append(edge.target)

        return result
