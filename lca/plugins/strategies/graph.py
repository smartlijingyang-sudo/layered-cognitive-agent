"""Graph strategy factory — registers into team_strategies.

同文件承载 GraphStrategy —— DAG 工作流引擎（resolved-counter 模型）：
将 ExecutionGraph 编译为拓扑排序执行计划，支持：
- 顺序边（FIXED）：前驱完成后触发后继
- 条件边（CONDITIONAL）：运行时求值 condition，命中则通行，否则级联跳过
- 并行边（PARALLEL）：多分支 asyncio.gather 并发执行
- 聚合节点（AGGREGATOR）：汇合多个前驱的输出

执行核心：BFS 队列驱动，resolved 计数器到齐即入队。单一解析入口
``resolve_successor``，消除旧 remaining 多路递减 bug。仅接受严格 DAG
（allow_cycle=False）。
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from typing import cast

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import GRAPH_NODE_EXECUTORS, STRATEGIES
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.result import Result
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.team.graph import EdgeType, ExecutionGraph, GraphNode, NodeType
from lca.contracts.models.team.team_coordination import STRATEGY_KEY_GRAPH, Graph
from lca.contracts.protocols import (
    GraphNodeExecutionContext,
    GraphNodeExecutorRegistryProtocol,
    StateStore,
    Synthesizer,
    TeamAssembly,
    TeamStage,
    TeamStrategy,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


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
    """DAG 工作流引擎：拓扑排序 + fan-in/fan-out + 条件分支 + 并行分支。

    构造期闭合（ADR-0034）：execution_graph 必填，舞台（成员 + 调用通道）
    构造期注入，运行期不解包任何上下文。
    """

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


# ── 拓扑操作（resolved-counter 模型，ADR-0034 修正）──
#
# 每个节点维护一个 ``resolved`` 计数器，每当一个前驱完成（执行、跳过、
# 或条件匹配）时 +1。当 ``resolved[node] == in_degree[node]`` 时节点就绪入队。
# 只有一个入口 ``resolve_successor``，所有路径（执行完成、级联跳过、
# 并行分支）统一调用，原子递增 + 到齐入队。


def compute_in_degree(
    graph: ExecutionGraph,
) -> dict[str, int]:
    """计算每个节点的入度（统计所有类型的入边）。"""
    in_degree: dict[str, int] = dict.fromkeys(graph.nodes, 0)
    for edge in graph.edges:
        in_degree[edge.target] += 1
    return in_degree


def resolve_successor(
    graph: ExecutionGraph,
    target_id: str,
    resolved: dict[str, int],
    in_degree: dict[str, int],
    enqueued: set[str],
    skipped: set[str],
    executed: set[str],
    queue: deque[str],
) -> None:
    """前驱完成（执行/跳过）时调用：递增 resolved，到齐则入队。

    幂等保护：已入队/已执行/已跳过的节点不会重复入队。
    """
    if target_id in enqueued or target_id in executed or target_id in skipped:
        return
    resolved[target_id] += 1
    if resolved[target_id] >= in_degree[target_id]:
        enqueued.add(target_id)
        queue.append(target_id)


def cascade_skip(
    graph: ExecutionGraph,
    node_id: str,
    resolved: dict[str, int],
    in_degree: dict[str, int],
    enqueued: set[str],
    skipped: set[str],
    executed: set[str],
    queue: deque[str],
) -> None:
    """条件边未命中时级联跳过下游节点。

    跳过节点后，对其每个后继调用 ``resolve_successor``——与正常执行完成
    相同的解析路径，确保 fan-in 节点正确收到"前驱已解决"信号。
    """
    skip_queue: deque[str] = deque([node_id])
    while skip_queue:
        nid = skip_queue.popleft()
        if nid in skipped or nid in executed or nid in enqueued:
            continue
        skipped.add(nid)
        for edge in graph.outgoing(nid):
            resolve_successor(
                graph,
                edge.target,
                resolved,
                in_degree,
                enqueued,
                skipped,
                executed,
                queue,
            )


# ── 结果聚合 —— 从执行结果中提取最终输出 ──


async def finalize_graph_result(
    objective: str,
    graph: ExecutionGraph,
    results: dict[str, Result],
    aggregator_ids: set[str],
    synthesizer: Synthesizer | None,
) -> Result:
    """从图执行结果中提取最终 Result：聚合器 > 终端节点 > synthesizer > 拼接。"""
    if not results:
        return Result.failed("Graph execution produced no results")
    total_steps = sum(r.total_steps for r in results.values())

    for agg_id in aggregator_ids:
        if agg_id in results and results[agg_id].output is not None:
            out = results[agg_id]
            out.total_steps = total_steps
            return out

    agent_ids = [
        nid
        for nid, r in results.items()
        if nid in graph.nodes and graph.nodes[nid].type == NodeType.AGENT and r.output
    ]
    terminal: list[str] = []
    for nid in agent_ids:
        has_agent_successor = any(
            e.target in graph.nodes and graph.nodes[e.target].type == NodeType.AGENT
            for e in graph.outgoing(nid)
        )
        if not has_agent_successor:
            terminal.append(nid)
    chosen = terminal or agent_ids
    parts = [str(results[nid].output) for nid in chosen if results[nid].output]

    if not parts:
        last = next(iter(results.values()))
        last.total_steps = total_steps
        return last
    if len(parts) == 1:
        for nid in chosen:
            if results[nid].output and str(results[nid].output) == parts[0]:
                r = results[nid]
                r.total_steps = total_steps
                return r
    if synthesizer is not None:
        candidates = [results[nid] for nid in chosen if results[nid].output]
        synthesized = await synthesizer.synthesize(objective, candidates)
        synthesized.total_steps = total_steps
        return synthesized
    budget = create_budget()
    budget.used_steps = total_steps
    return Result(
        trace_id=objective[:16],
        status=TaskStatus.COMPLETED,
        final_state_ref="",
        total_steps=total_steps,
        budget_used=budget,
        output="\n".join(parts),
    )


def build_graph_strategy(
    assembly: TeamAssembly,
    *,
    node_executors: GraphNodeExecutorRegistryProtocol,
) -> GraphStrategy:
    """Close GraphStrategy with the Profile-selected node primitive registry."""

    governance = assembly.governance
    if not isinstance(governance, Graph):
        raise TypeError(f"strategy {STRATEGY_KEY_GRAPH!r} requires Graph governance")
    return GraphStrategy(
        assembly.stage,
        execution_graph=governance.execution_graph,
        node_executors=node_executors,
    )


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="strategy.graph",
    requires=[STRATEGIES.key, GRAPH_NODE_EXECUTORS.key],
    layer="L3",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description="Register graph TeamStrategy factory.",
    test_suite="tests/test_graph_strategy.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("strategy_graph.checked", "strategy_graph.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    node_executors = cast(
        "GraphNodeExecutorRegistryProtocol",
        ctx.require(GRAPH_NODE_EXECUTORS.key),
    )
    ctx.register(
        STRATEGIES.key,
        STRATEGY_KEY_GRAPH,
        lambda assembly: build_graph_strategy(assembly, node_executors=node_executors),
    )
