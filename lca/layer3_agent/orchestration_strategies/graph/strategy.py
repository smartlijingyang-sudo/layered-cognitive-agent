"""GraphStrategy —— DAG workflow engine with fan-in visibility."""

from __future__ import annotations

import asyncio
from collections import deque
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


class GraphStrategy(OrchestrationStrategy):
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
        state = TypedState(trace_id="graph", task=objective, budget=Budget())
        in_degree, out_edge_indices = compute_in_degree_and_out_edges(graph)
        remaining: dict[str, int] = dict(in_degree)
        executed: set[str] = set()
        skipped: set[str] = set()
        results: dict[str, Result] = {}
        aggregator_ids: set[str] = set()
        queue: deque[str] = deque(nid for nid, deg in remaining.items() if deg == 0)
        while queue:
            nid = queue.popleft()
            if nid in executed or nid in skipped:
                continue
            node = graph.nodes[nid]
            if node.type == NodeType.AGGREGATOR:
                aggregator_ids.add(nid)
            await self._execute_node(node, graph, context, member_map, objective, state, results)
            executed.add(nid)
            fixed_targets: list[str] = []
            parallel_targets: list[str] = []
            for edge_idx in out_edge_indices[nid]:
                edge = graph.edges[edge_idx]
                if edge.type == EdgeType.CONDITIONAL:
                    if edge.condition is not None and edge.condition(state):
                        fixed_targets.append(edge.target)
                    else:
                        cascade_skip(graph, edge.target, remaining, skipped, executed, queue)
                elif edge.type == EdgeType.PARALLEL:
                    parallel_targets.append(edge.target)
                else:
                    fixed_targets.append(edge.target)
            if parallel_targets:
                await self._execute_parallel_branches(
                    parallel_targets,
                    graph,
                    context,
                    member_map,
                    objective,
                    state,
                    results,
                    remaining,
                    executed,
                    skipped,
                    queue,
                    aggregator_ids,
                )
            else:
                enqueue_ready_targets(fixed_targets, remaining, executed, queue)
        return self._finalize(graph, results, aggregator_ids)

    def _resolve_graph(self, context: OrchestrationContext) -> ExecutionGraph:
        if self._graph is not None:
            return self._graph
        raise ValueError("GraphStrategy 需要 ExecutionGraph：构造时传入 execution_graph")

    async def _execute_node(
        self,
        node: Any,
        graph: ExecutionGraph,
        context: OrchestrationContext,
        member_map: dict[str, Any],
        objective: str,
        state: TypedState,
        results: dict[str, Result],
    ) -> None:
        if node.type == NodeType.AGENT:
            role = node.config.get("role", "")
            member = member_map.get(role)
            if member:
                results[node.id] = await invoke_member(context, member, objective)
                if self._state_store:
                    await self._state_store.save(state)
        elif node.type == NodeType.AGGREGATOR:
            preds = [e.source for e in graph.incoming(node.id)]
            parts = [str(results[p].output) for p in preds if p in results and results[p].output]
            total_steps = sum(results[p].total_steps for p in preds if p in results)
            results[node.id] = Result(
                trace_id="graph-agg",
                status=TaskStatus.COMPLETED,
                final_state_ref="",
                total_steps=total_steps or 1,
                budget_used=Budget(used_steps=total_steps or 1),
                output="\n".join(parts),
            )

    async def _execute_parallel_branches(
        self,
        targets: list[str],
        graph: ExecutionGraph,
        context: OrchestrationContext,
        member_map: dict[str, Any],
        objective: str,
        state: TypedState,
        results: dict[str, Result],
        remaining: dict[str, int],
        executed: set[str],
        skipped: set[str],
        queue: deque[str],
        aggregator_ids: set[str],
    ) -> None:
        async def _run_branch(target_nid: str) -> None:
            if target_nid in executed or target_nid in skipped:
                return
            node = graph.nodes[target_nid]
            if node.type == NodeType.AGGREGATOR:
                aggregator_ids.add(target_nid)
            await self._execute_node(node, graph, context, member_map, objective, state, results)
            executed.add(target_nid)
            sub_fixed: list[str] = []
            sub_parallel: list[str] = []
            for edge in graph.outgoing(target_nid):
                if edge.type == EdgeType.PARALLEL:
                    sub_parallel.append(edge.target)
                elif edge.type == EdgeType.CONDITIONAL:
                    if edge.condition is not None and edge.condition(state):
                        sub_fixed.append(edge.target)
                    else:
                        cascade_skip(graph, edge.target, remaining, skipped, executed, queue)
                else:
                    sub_fixed.append(edge.target)
            if sub_parallel:
                await self._execute_parallel_branches(
                    sub_parallel,
                    graph,
                    context,
                    member_map,
                    objective,
                    state,
                    results,
                    remaining,
                    executed,
                    skipped,
                    queue,
                    aggregator_ids,
                )
            else:
                for sub_target in sub_fixed:
                    remaining[sub_target] -= 1
                    if remaining[sub_target] <= 0 and sub_target not in executed:
                        await _run_branch(sub_target)

        await asyncio.gather(*[_run_branch(t) for t in targets])
        for target in targets:
            for edge in graph.outgoing(target):
                next_nid = edge.target
                remaining[next_nid] -= 1
                if remaining[next_nid] <= 0 and next_nid not in executed:
                    queue.append(next_nid)

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
            trace_id="graph",
            status=TaskStatus.COMPLETED,
            final_state_ref="",
            total_steps=total_steps,
            budget_used=Budget(used_steps=total_steps),
            output="\n".join(parts),
        )
