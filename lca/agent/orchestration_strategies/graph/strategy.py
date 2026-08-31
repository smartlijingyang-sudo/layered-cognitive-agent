"""GraphStrategy —— DAG 工作流引擎（resolved-counter 模型）。

L3 层职责：
    将 ExecutionGraph 编译为拓扑排序执行计划，支持：
    - 顺序边（FIXED）：前驱完成后触发后继
    - 条件边（CONDITIONAL）：运行时求值 condition，命中则通行，否则级联跳过
    - 并行边（PARALLEL）：多分支 asyncio.gather 并发执行
    - 聚合节点（AGGREGATOR）：汇合多个前驱的输出

    执行核心：BFS 队列驱动，resolved 计数器到齐即入队。
    单一解析入口 ``resolve_successor``，消除旧 remaining 多路递减 bug。
    仅接受严格 DAG（allow_cycle=False）。

构造期闭合（ADR-0034）：execution_graph 必填，舞台（成员 + 调用通道）
构造期注入，运行期不解包任何上下文。
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field

from lca.agent.orchestration_strategies.graph._finalize import (
    finalize_graph_result,
)
from lca.agent.orchestration_strategies.graph.topology import (
    cascade_skip,
    compute_in_degree,
    resolve_successor,
)
from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.result import Result
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.team.graph import EdgeType, ExecutionGraph, GraphNode
from lca.contracts.protocols import (
    GraphNodeExecutionContext,
    GraphNodeExecutorRegistryProtocol,
    StateStore,
    Synthesizer,
    TeamStage,
    TeamStrategy,
)


@dataclass
class GraphExecutionState:
    """BFS 执行状态 —— resolved-counter 模型。

    ``resolved[node]`` 记录已完成前驱数；``in_degree[node]`` 记录总前驱数。
    当 resolved == in_degree 时节点就绪入队。
    ``successors_done`` 防止主循环和并行分支重复处理同一节点的出边。

    每次 run() 创建新实例，无跨调用共享。
    """

    in_degree: dict[str, int]
    resolved: dict[str, int] = field(default_factory=dict)
    enqueued: set[str] = field(default_factory=set)
    executed: set[str] = field(default_factory=set)
    skipped: set[str] = field(default_factory=set)
    successors_done: set[str] = field(default_factory=set)
    results: dict[str, Result] = field(default_factory=dict)
    aggregator_ids: set[str] = field(default_factory=set)
    queue: deque[str] = field(default_factory=deque)


class GraphStrategy(TeamStrategy):
    """DAG 工作流引擎：拓扑排序 + fan-in/fan-out + 条件分支 + 并行分支。"""

    def __init__(
        self,
        stage: TeamStage,
        execution_graph: ExecutionGraph,
        node_executors: GraphNodeExecutorRegistryProtocol,
        state_store: StateStore | None = None,
        synthesizer: Synthesizer | None = None,
    ) -> None:
        self._stage = stage
        self._graph = execution_graph
        self._node_executors = node_executors
        self._state_store = state_store
        self._synthesizer = synthesizer

    async def run(self, objective: str) -> Result:
        graph = self._graph
        graph.validate()
        if graph.allow_cycle:
            raise ValueError("GraphStrategy 仅支持严格 DAG（allow_cycle=False)。")
        state = AgentState(trace_id=objective[:16], task=objective, budget=create_budget())
        in_degree = compute_in_degree(graph)

        roots = [nid for nid, deg in in_degree.items() if deg == 0]
        es = GraphExecutionState(
            in_degree=in_degree,
            resolved=dict.fromkeys(graph.nodes, 0),
            queue=deque(roots),
            enqueued=set(roots),
        )

        while es.queue:
            nid = es.queue.popleft()
            if nid in es.executed or nid in es.skipped:
                continue
            node = graph.nodes[nid]
            await self._execute_node(node, graph, objective, state, es)
            es.executed.add(nid)
            await self._process_outgoing(nid, graph, state, es, objective)

        return await finalize_graph_result(
            objective, graph, es.results, es.aggregator_ids, self._synthesizer
        )

    async def _process_outgoing(
        self,
        nid: str,
        graph: ExecutionGraph,
        state: AgentState,
        es: GraphExecutionState,
        objective: str,
    ) -> None:
        """处理节点出边：分类 → 条件求值 → 并行执行子树 → resolve 后继。

        每个节点的出边只处理一次（``successors_done`` 守卫）。
        并行分支递归处理完整子树（执行 + 出边 + resolve），
        确保并行分支的后继在 gather 返回前已 resolve。
        """
        if nid in es.successors_done:
            return
        es.successors_done.add(nid)

        fixed: list[str] = []
        parallel: list[str] = []

        for edge in graph.outgoing(nid):
            if edge.type == EdgeType.CONDITIONAL:
                if edge.condition is not None and edge.condition(state):
                    fixed.append(edge.target)
                else:
                    cascade_skip(
                        graph,
                        edge.target,
                        es.resolved,
                        es.in_degree,
                        es.enqueued,
                        es.skipped,
                        es.executed,
                        es.queue,
                    )
            elif edge.type == EdgeType.PARALLEL:
                parallel.append(edge.target)
            else:
                fixed.append(edge.target)

        if parallel:
            await self._execute_parallel_branches(parallel, graph, state, es, objective)
        for target in fixed:
            resolve_successor(
                graph,
                target,
                es.resolved,
                es.in_degree,
                es.enqueued,
                es.skipped,
                es.executed,
                es.queue,
            )

    async def _execute_parallel_branches(
        self,
        targets: list[str],
        graph: ExecutionGraph,
        state: AgentState,
        es: GraphExecutionState,
        objective: str,
    ) -> None:
        """并发执行并行分支，每个分支递归处理完整子树。"""

        async def _run_branch(target_nid: str) -> None:
            if target_nid in es.executed or target_nid in es.skipped:
                return
            node = graph.nodes[target_nid]
            await self._execute_node(node, graph, objective, state, es)
            es.executed.add(target_nid)
            await self._process_outgoing(target_nid, graph, state, es, objective)

        await asyncio.gather(*[_run_branch(t) for t in targets], return_exceptions=True)

    async def _execute_node(
        self,
        node: GraphNode,
        graph: ExecutionGraph,
        objective: str,
        state: AgentState,
        es: GraphExecutionState,
    ) -> None:
        """Delegate one node's behavior to its profile-selected primitive."""

        executor = self._node_executors.resolve(node.type)
        if executor.is_aggregator:
            es.aggregator_ids.add(node.id)
        result = await executor.execute(
            GraphNodeExecutionContext(
                node=node,
                graph=graph,
                objective=objective,
                state=state,
                stage=self._stage,
                predecessor_results=es.results,
                state_store=self._state_store,
            )
        )
        if result is not None:
            es.results[node.id] = result
