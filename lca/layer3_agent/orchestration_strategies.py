"""编排策略实现 —— hierarchical / sequential / parallel / graph / debate。"""

from __future__ import annotations

import asyncio
import uuid
from collections import deque
from typing import Any, cast

from lca.contracts.decision import StructuredDecision
from lca.contracts.graph import ExecutionGraph
from lca.contracts.protocols import (
    ConflictMonitor,
    OrchestrationContext,
    OrchestrationStrategy,
    StateEvaluator,
    StateStore,
    Synthesizer,
    TaskCoordinator,
)
from lca.contracts.result import Result
from lca.contracts.state import Budget, TypedState


class HierarchicalStrategy(OrchestrationStrategy):
    """Supervisor 单向委派、汇总。"""

    async def run(self, context: OrchestrationContext, objective: str) -> Result:
        if context.supervisor is None:
            raise ValueError("Hierarchical 模式需要 Supervisor")
        if context.transport is not None:
            context.supervisor.bind_team(context.transport, context.roster_desc)
        return cast("Result", await context.supervisor.execute(objective))


class SequentialStrategy(OrchestrationStrategy):
    """任务像流水线一样在成员间顺序传递。"""

    async def run(self, context: OrchestrationContext, objective: str) -> Result:
        current_task = objective
        last_result: Result | None = None
        for member in context.members:
            last_result = await member.execute(current_task)
            if last_result.output:
                current_task = last_result.output
        return last_result or Result(
            trace_id="",
            status="failed",
            final_state_ref="",
            total_steps=0,
            budget_used=None,  # type: ignore[arg-type]
            error="No members in team",
        )


class ParallelStrategy(OrchestrationStrategy):
    """scatter-gather 并行：同一任务分发给所有成员并发执行，通过 Synthesizer 聚合结果。

    本质是 GraphStrategy 的特例（"所有节点入边相同、无依赖"），
    用 asyncio.gather 实现并发调度。

    fan-in 阶段由可插拔的 Synthesizer 完成：
    - ConcatSynthesizer（默认）：简单拼接所有候选输出
    - LLMSynthesizer：调用 LLM 做 Layer-2 提炼（MoA 核心）
    - BestOfSynthesizer：复用 TaskCoordinator.arbitrate 选优
    """

    def __init__(self, synthesizer: Synthesizer | None = None) -> None:
        self._synthesizer = synthesizer

    async def run(self, context: OrchestrationContext, objective: str) -> Result:
        if not context.members:
            return Result(
                trace_id="",
                status="failed",
                final_state_ref="",
                total_steps=0,
                budget_used=None,  # type: ignore[arg-type]
                error="No members in team",
            )
        tasks = [member.execute(objective) for member in context.members]
        results: list[Result] = await asyncio.gather(*tasks)

        if self._synthesizer is not None:
            return await self._synthesizer.synthesize(objective, results)

        return results[-1]


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

        # 计算入度和出边索引
        in_degree: dict[str, int] = dict.fromkeys(self._graph.nodes, 0)
        out_edge_indices: dict[str, list[int]] = {nid: [] for nid in self._graph.nodes}
        for idx, edge in enumerate(self._graph.edges):
            in_degree[edge.target] += 1
            out_edge_indices[edge.source].append(idx)

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

            # 执行 agent 节点
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

            # 分类出边
            fixed_targets: list[str] = []
            parallel_targets: list[str] = []

            for edge_idx in out_edge_indices[nid]:
                edge = self._graph.edges[edge_idx]
                if edge.type == "conditional":
                    if edge.condition is not None and edge.condition(state):
                        fixed_targets.append(edge.target)
                    else:
                        self._cascade_skip(edge.target, remaining, skipped, executed, queue)
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
                for target in fixed_targets:
                    remaining[target] -= 1
                    if remaining[target] <= 0 and target not in executed:
                        queue.append(target)

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
                        self._cascade_skip(edge.target, remaining, skipped, executed, queue)
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

        # 并行分支完成后，通知汇聚点
        for target in targets:
            for edge in self._graph.outgoing(target):  # type: ignore[union-attr]
                next_nid = edge.target
                remaining[next_nid] -= 1
                if remaining[next_nid] <= 0 and next_nid not in executed:
                    queue.append(next_nid)

    def _cascade_skip(
        self,
        node_id: str,
        remaining: dict[str, int],
        skipped: set[str],
        executed: set[str],
        queue: deque[str],
    ) -> None:
        """条件边未命中时级联跳过下游节点，防止 join 死等。"""
        skip_queue: deque[str] = deque([node_id])
        while skip_queue:
            nid = skip_queue.popleft()
            if nid in skipped or nid in executed:
                continue
            remaining[nid] -= 1
            if remaining[nid] > 0:
                continue
            skipped.add(nid)
            for edge in self._graph.outgoing(nid):  # type: ignore[union-attr]
                if edge.target not in executed:
                    skip_queue.append(edge.target)


_DEFAULT_MAX_ROUNDS = 3


class DebateStrategy(OrchestrationStrategy):
    """多 Agent 辩论达成共识。

    每轮用 asyncio.gather 并行收集各 Agent 对当前 objective 的表态，
    轮间通过 ConflictMonitor.check 判断是否仍有分歧（无分歧则提前退出），
    最终由 StateEvaluator.score + TaskCoordinator.arbitrate 选出最优方案。

    复用 L1 MAP 五模块中的 ConflictMonitor / StateEvaluator / TaskCoordinator，
    验证"单 Agent 内部积木可直接复用为跨 Agent 编排能力"这一架构假设。
    """

    def __init__(
        self,
        conflict_monitor: ConflictMonitor | None = None,
        task_coordinator: TaskCoordinator | None = None,
        state_evaluator: StateEvaluator | None = None,
    ) -> None:
        self._conflict_monitor = conflict_monitor
        self._task_coordinator = task_coordinator
        self._state_evaluator = state_evaluator

    async def run(self, context: OrchestrationContext, objective: str) -> Result:
        if not context.members:
            return Result(
                trace_id="",
                status="failed",
                final_state_ref="",
                total_steps=0,
                budget_used=None,  # type: ignore[arg-type]
                error="No members in team",
            )

        max_rounds = (
            context.config.max_rounds
            if context.config and context.config.max_rounds
            else _DEFAULT_MAX_ROUNDS
        )

        current_objective = objective
        all_round_results: list[list[Result]] = []

        for _round in range(max_rounds):
            tasks = [member.execute(current_objective) for member in context.members]
            round_results: list[Result] = await asyncio.gather(*tasks)
            all_round_results.append(round_results)

            conflicts = await self._check_conflicts(objective, round_results)
            if not conflicts:
                return await self._arbitrate(objective, round_results)

            proposals = "\n".join(
                f"Agent {i}: {r.output or ''}" for i, r in enumerate(round_results)
            )
            current_objective = f"{objective}\n\nPrevious proposals:\n{proposals}"

        final_round = all_round_results[-1]
        return await self._arbitrate(objective, final_round)

    async def _check_conflicts(self, objective: str, results: list[Result]) -> list[str]:
        if self._conflict_monitor is None:
            return ["no_monitor"]
        state = TypedState(trace_id="debate", task=objective, budget=Budget())
        decisions = [_result_to_decision(r, i) for i, r in enumerate(results)]
        return await self._conflict_monitor.check(state, decisions)

    async def _arbitrate(self, objective: str, results: list[Result]) -> Result:
        if self._task_coordinator is None or self._state_evaluator is None:
            return (
                results[0]
                if results
                else Result(
                    trace_id="",
                    status="failed",
                    final_state_ref="",
                    total_steps=0,
                    budget_used=None,  # type: ignore[arg-type]
                    error="No results to arbitrate",
                )
            )
        state = TypedState(trace_id="debate", task=objective, budget=Budget())
        decisions = [_result_to_decision(r, i) for i, r in enumerate(results)]
        scores = [
            await self._state_evaluator.score(state, {"decision": d.rationale}) for d in decisions
        ]
        await self._task_coordinator.arbitrate(state, decisions, scores)
        best_idx = max(range(len(scores)), key=lambda i: scores[i])
        return results[best_idx]


class HandoffStrategy(OrchestrationStrategy):
    """动态控制权移交：按顺序将任务交给各 Agent，任一 Agent 完成即终止。

    与 SequentialStrategy 的区别：
    - Sequential：每个 Agent 都必须执行，像流水线一样传递
    - Handoff：第一个能完成任务的 Agent 执行后，后续 Agent 不再执行

    典型场景：客服分诊（分诊 Agent → 专家 Agent），不需要分诊 Agent 等结果。
    """

    async def run(self, context: OrchestrationContext, objective: str) -> Result:
        if not context.members:
            return Result(
                trace_id="",
                status="failed",
                final_state_ref="",
                total_steps=0,
                budget_used=None,  # type: ignore[arg-type]
                error="No members in team",
            )

        last_result: Result | None = None
        for member in context.members:
            result: Result = await member.execute(objective)
            last_result = result
            if result.status == "completed":
                return result

        return last_result or Result(
            trace_id="",
            status="failed",
            final_state_ref="",
            total_steps=0,
            budget_used=None,  # type: ignore[arg-type]
            error="All members failed",
        )


def _result_to_decision(result: Result, index: int) -> StructuredDecision:
    return StructuredDecision(
        decision_id=f"debate_{index}_{uuid.uuid4().hex[:8]}",
        action_type="respond",
        rationale=result.output or "",
        confidence=0.5,
        response_text=result.output,
    )
