"""GraphStrategy —— DAG 工作流引擎。

L3 层职责：
    将 ExecutionGraph 编译为拓扑排序执行计划，支持：
    - 顺序边（DEFAULT）：前驱完成后触发后继
    - 条件边（CONDITIONAL）：运行时求值 condition，命中则通行，否则级联跳过
    - 并行边（PARALLEL）：多分支 asyncio.gather 并发执行
    - 聚合节点（AGGREGATOR）：汇合多个前驱的输出

    执行核心：BFS 队列驱动拓扑排序，入度归零即入队。
    仅接受严格 DAG（allow_cycle=False）。
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from lca.contracts.graph import EdgeType, ExecutionGraph, NodeType
from lca.contracts.lifecycle import TaskStatus
from lca.contracts.protocols import OrchestrationContext, OrchestrationStrategy, StateStore
from lca.contracts.result import Result
from lca.contracts.state import Budget, TypedState
from lca.layer3_agent.member_invoke import invoke_member
from lca.layer3_agent.orchestration_strategies.graph.topology import (
    cascade_skip,
    compute_in_degree_and_out_edges,
    enqueue_ready_targets,
)

_AGGREGATOR_TRACE_PREFIX = "graph-agg"
_GRAPH_TRACE_ID = "graph"


@dataclass
class GraphExecutionState:
    """BFS 执行状态 —— 将原 12 参数递归收敛为一个可变状态对象。

    每次 run() 创建新实例，无跨调用共享。
    """

    remaining: dict[str, int]
    executed: set[str] = field(default_factory=set)
    skipped: set[str] = field(default_factory=set)
    results: dict[str, Result] = field(default_factory=dict)
    aggregator_ids: set[str] = field(default_factory=set)
    queue: deque[str] = field(default_factory=deque)


class GraphStrategy(OrchestrationStrategy):
    """DAG 工作流引擎：拓扑排序 + fan-in/fan-out + 条件分支 + 并行分支。

    构造时可选传入 ExecutionGraph 和 StateStore。
    若未传入 graph，则从 OrchestrationContext 解析（当前要求构造时传入）。
    """

    def __init__(
        self,
        execution_graph: ExecutionGraph | None = None,
        state_store: StateStore | None = None,
    ) -> None:
        self._graph = execution_graph
        self._state_store = state_store

    async def run(self, context: OrchestrationContext, objective: str) -> Result:
        graph = self._resolve_graph(context)
        graph.validate()
        if graph.allow_cycle:
            raise ValueError("GraphStrategy 仅支持严格 DAG（allow_cycle=False）。")
        member_map = {m.role_profile.role: m for m in context.members}
        state = TypedState(trace_id=_GRAPH_TRACE_ID, task=objective, budget=Budget())
        in_degree, out_edge_indices = compute_in_degree_and_out_edges(graph)

        es = GraphExecutionState(
            remaining=dict(in_degree),
            queue=deque(nid for nid, deg in in_degree.items() if deg == 0),
        )

        while es.queue:
            nid = es.queue.popleft()
            if nid in es.executed or nid in es.skipped:
                continue
            node = graph.nodes[nid]
            if node.type == NodeType.AGGREGATOR:
                es.aggregator_ids.add(nid)
            await self._execute_node(node, graph, context, member_map, objective, state, es)
            es.executed.add(nid)
            await self._process_outgoing(
                nid, graph, state, out_edge_indices, es, context, member_map, objective
            )

        return self._finalize(graph, es.results, es.aggregator_ids)

    async def _process_outgoing(
        self,
        nid: str,
        graph: ExecutionGraph,
        state: TypedState,
        out_edge_indices: dict[str, list[int]],
        es: GraphExecutionState,
        context: OrchestrationContext,
        member_map: dict[str, Any],
        objective: str,
    ) -> None:
        """处理节点出边：分类为 fixed / parallel / conditional，驱动后续执行。"""
        fixed_targets: list[str] = []
        parallel_targets: list[str] = []
        for edge_idx in out_edge_indices[nid]:
            edge = graph.edges[edge_idx]
            if edge.type == EdgeType.CONDITIONAL:
                if edge.condition is not None and edge.condition(state):
                    fixed_targets.append(edge.target)
                else:
                    cascade_skip(
                        graph, edge.target, es.remaining, es.skipped, es.executed, es.queue
                    )
            elif edge.type == EdgeType.PARALLEL:
                parallel_targets.append(edge.target)
            else:
                fixed_targets.append(edge.target)
        if parallel_targets:
            await self._execute_parallel_branches(
                parallel_targets, graph, context, member_map, objective, state, es
            )
        else:
            enqueue_ready_targets(fixed_targets, es.remaining, es.executed, es.queue)

    async def _execute_parallel_branches(
        self,
        targets: list[str],
        graph: ExecutionGraph,
        context: OrchestrationContext,
        member_map: dict[str, Any],
        objective: str,
        state: TypedState,
        es: GraphExecutionState,
    ) -> None:
        """并行执行多个分支（asyncio.gather），每个分支可递归触发子并行。"""

        async def _run_branch(target_nid: str) -> None:
            if target_nid in es.executed or target_nid in es.skipped:
                return
            node = graph.nodes[target_nid]
            if node.type == NodeType.AGGREGATOR:
                es.aggregator_ids.add(target_nid)
            await self._execute_node(node, graph, context, member_map, objective, state, es)
            es.executed.add(target_nid)

            sub_fixed: list[str] = []
            sub_parallel: list[str] = []
            for edge in graph.outgoing(target_nid):
                if edge.type == EdgeType.PARALLEL:
                    sub_parallel.append(edge.target)
                elif edge.type == EdgeType.CONDITIONAL:
                    if edge.condition is not None and edge.condition(state):
                        sub_fixed.append(edge.target)
                    else:
                        cascade_skip(
                            graph, edge.target, es.remaining, es.skipped, es.executed, es.queue
                        )
                else:
                    sub_fixed.append(edge.target)
            if sub_parallel:
                await self._execute_parallel_branches(
                    sub_parallel, graph, context, member_map, objective, state, es
                )
            else:
                for sub_target in sub_fixed:
                    es.remaining[sub_target] -= 1
                    if es.remaining[sub_target] <= 0 and sub_target not in es.executed:
                        await _run_branch(sub_target)

        await asyncio.gather(*[_run_branch(t) for t in targets])
        for target in targets:
            for edge in graph.outgoing(target):
                next_nid = edge.target
                es.remaining[next_nid] -= 1
                if es.remaining[next_nid] <= 0 and next_nid not in es.executed:
                    es.queue.append(next_nid)

    async def _execute_node(
        self,
        node: Any,
        graph: ExecutionGraph,
        context: OrchestrationContext,
        member_map: dict[str, Any],
        objective: str,
        state: TypedState,
        es: GraphExecutionState,
    ) -> None:
        if node.type == NodeType.AGENT:
            role = node.config.get("role", "")
            member = member_map.get(role)
            if member:
                es.results[node.id] = await invoke_member(context, member, objective)
                if self._state_store:
                    await self._state_store.save(state)
        elif node.type == NodeType.AGGREGATOR:
            preds = [e.source for e in graph.incoming(node.id)]
            parts = [
                str(es.results[p].output) for p in preds if p in es.results and es.results[p].output
            ]
            total_steps = sum(es.results[p].total_steps for p in preds if p in es.results)
            es.results[node.id] = Result(
                trace_id=_AGGREGATOR_TRACE_PREFIX,
                status=TaskStatus.COMPLETED,
                final_state_ref="",
                total_steps=total_steps or 1,
                budget_used=Budget(used_steps=total_steps or 1),
                output="\n".join(parts),
            )

    def _resolve_graph(self, context: OrchestrationContext) -> ExecutionGraph:
        if self._graph is not None:
            return self._graph
        raise ValueError("GraphStrategy 需要 ExecutionGraph：构造时传入 execution_graph")

    @staticmethod
    def _finalize(
        graph: ExecutionGraph, results: dict[str, Result], aggregator_ids: set[str]
    ) -> Result:
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
            outs = [
                e.target
                for e in graph.outgoing(nid)
                if e.target in results
                and e.target in graph.nodes
                and graph.nodes[e.target].type == NodeType.AGENT
            ]
            if not outs:
                terminal.append(nid)
        chosen = terminal or agent_ids
        parts = [str(results[nid].output) for nid in chosen if results[nid].output]
        if not parts:
            last = next(iter(results.values()))
            last.total_steps = total_steps
            return last
        if len(parts) == 1:
            for nid in chosen:
                if str(results[nid].output) == parts[0]:
                    r = results[nid]
                    r.total_steps = total_steps
                    return r
        return Result(
            trace_id=_GRAPH_TRACE_ID,
            status=TaskStatus.COMPLETED,
            final_state_ref="",
            total_steps=total_steps,
            budget_used=Budget(used_steps=total_steps),
            output="\n".join(parts),
        )
