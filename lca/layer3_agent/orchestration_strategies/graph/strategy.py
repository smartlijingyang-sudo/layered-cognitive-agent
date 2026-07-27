"""GraphStrategy —— 基于 DAG 的自定义工作流执行引擎。"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

from lca.contracts.graph import ExecutionGraph
from lca.contracts.protocols import (
    OrchestrationContext,
    OrchestrationStrategy,
    StateStore,
)
from lca.contracts.result import Result
from lca.contracts.state import Budget, TypedState
from lca.layer3_agent.orchestration_strategies.graph.topology import (
    cascade_skip,
    compute_in_degree_and_out_edges,
    enqueue_ready_targets,
)


class GraphStrategy(OrchestrationStrategy):
    """基于 DAG 的自定义工作流执行引擎。

    支持三种边类型：
    - fixed: 固定流转
    - conditional: 条件分支（condition 函数返回 bool 决定是否走该边）
    - parallel: 并行扇出，asyncio.gather 并发执行所有目标，全部完成后汇聚

    执行模型：基于入度（in-degree）的拓扑排序驱动。
    每个节点等待所有前驱完成（或跳过）后才执行，天然支持 fan-in 汇聚。
    条件边跳过时级联通知下游，避免 join 节点死等。

    可选注入 StateStore 做 checkpoint（on_error 回滚预留，复用已有 StateSnapshot.reason）。
    """

    def __init__(
        self,
        execution_graph: ExecutionGraph | None = None,
        state_store: StateStore | None = None,
    ) -> None:
        self._graph = execution_graph
        self._state_store = state_store

    async def run(self, context: OrchestrationContext, objective: str) -> Result:
        if self._graph is None:
            raise ValueError("GraphStrategy 需要 ExecutionGraph，请在构造时传入 execution_graph")

        self._graph.validate()

        member_map = {m.role_profile.role: m for m in context.members}
        state = TypedState(trace_id="graph", task=objective, budget=Budget())

        in_degree, out_edge_indices = compute_in_degree_and_out_edges(self._graph)

        remaining: dict[str, int] = dict(in_degree)
        executed: set[str] = set()
        skipped: set[str] = set()
        results: dict[str, Result] = {}
        last_result: Result | None = None

        queue: deque[str] = deque(nid for nid, deg in remaining.items() if deg == 0)

        while queue:
            nid = queue.popleft()
            if nid in executed or nid in skipped:
                continue

            node = self._graph.nodes[nid]

            if node.type == "agent":
                role = node.config.get("role", "")
                member = member_map.get(role)
                if member:
                    result = await member.execute(objective)
                    results[nid] = result
                    last_result = result
                    if self._state_store:
                        await self._state_store.save(state)

            executed.add(nid)

            fixed_targets: list[str] = []
            parallel_targets: list[str] = []

            for edge_idx in out_edge_indices[nid]:
                edge = self._graph.edges[edge_idx]
                if edge.type == "conditional":
                    if edge.condition is not None and edge.condition(state):
                        fixed_targets.append(edge.target)
                    else:
                        cascade_skip(self._graph, edge.target, remaining, skipped, executed, queue)
                elif edge.type == "parallel":
                    parallel_targets.append(edge.target)
                else:
                    fixed_targets.append(edge.target)

            if parallel_targets:
                await self._execute_parallel_branches(
                    parallel_targets,
                    member_map,
                    objective,
                    state,
                    results,
                    remaining,
                    executed,
                    skipped,
                    queue,
                )
            else:
                enqueue_ready_targets(fixed_targets, remaining, executed, queue)

        return last_result or Result(
            trace_id="",
            status="failed",
            final_state_ref="",
            total_steps=0,
            budget_used=None,  # type: ignore[arg-type]
            error="Graph execution produced no results",
        )

    async def _execute_parallel_branches(
        self,
        targets: list[str],
        member_map: dict[str, Any],
        objective: str,
        state: TypedState,
        results: dict[str, Result],
        remaining: dict[str, int],
        executed: set[str],
        skipped: set[str],
        queue: deque[str],
    ) -> None:
        """并行扇出：asyncio.gather 并发执行所有目标子图，全部完成后汇聚。"""

        async def _run_branch(target_nid: str) -> None:
            if target_nid in executed or target_nid in skipped:
                return
            node = self._graph.nodes[target_nid]  # type: ignore[union-attr]

            if node.type == "agent":
                role = node.config.get("role", "")
                member = member_map.get(role)
                if member:
                    results[target_nid] = await member.execute(objective)

            executed.add(target_nid)

            sub_fixed: list[str] = []
            sub_parallel: list[str] = []
            for edge in self._graph.outgoing(target_nid):  # type: ignore[union-attr]
                if edge.type == "parallel":
                    sub_parallel.append(edge.target)
                elif edge.type == "conditional":
                    if edge.condition is not None and edge.condition(state):
                        sub_fixed.append(edge.target)
                    else:
                        cascade_skip(
                            self._graph,  # type: ignore[arg-type]
                            edge.target,
                            remaining,
                            skipped,
                            executed,
                            queue,
                        )
                else:
                    sub_fixed.append(edge.target)

            if sub_parallel:
                await self._execute_parallel_branches(
                    sub_parallel,
                    member_map,
                    objective,
                    state,
                    results,
                    remaining,
                    executed,
                    skipped,
                    queue,
                )
            else:
                for sub_target in sub_fixed:
                    remaining[sub_target] -= 1
                    if remaining[sub_target] <= 0 and sub_target not in executed:
                        await _run_branch(sub_target)

        await asyncio.gather(*[_run_branch(t) for t in targets])

        for target in targets:
            for edge in self._graph.outgoing(target):  # type: ignore[union-attr]
                next_nid = edge.target
                remaining[next_nid] -= 1
                if remaining[next_nid] <= 0 and next_nid not in executed:
                    queue.append(next_nid)
