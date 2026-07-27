"""DebateStrategy —— 多 Agent 辩论达成共识。"""

from __future__ import annotations

import asyncio
import uuid

from lca.contracts.decision import StructuredDecision
from lca.contracts.protocols import (
    ConflictMonitor,
    OrchestrationContext,
    OrchestrationStrategy,
    StateEvaluator,
    TaskCoordinator,
)
from lca.contracts.result import Result
from lca.contracts.state import Budget, TypedState

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


def _result_to_decision(result: Result, index: int) -> StructuredDecision:
    return StructuredDecision(
        decision_id=f"debate_{index}_{uuid.uuid4().hex[:8]}",
        action_type="respond",
        rationale=result.output or "",
        confidence=0.5,
        response_text=result.output,
    )
