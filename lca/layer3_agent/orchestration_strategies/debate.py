"""DebateStrategy —— 多 Agent 辩论达成共识。"""

from __future__ import annotations

import asyncio

from lca.contracts.decision import Decision
from lca.contracts.enums import ActionType
from lca.contracts.protocols import (
    CandidateEvaluationPipeline,
    TeamContext,
    TeamProcessStrategy,
)
from lca.contracts.result import Result
from lca.contracts.state import AgentState, Budget
from lca.layer3_agent.member_invoke import invoke_member

_DEFAULT_MAX_ROUNDS = 3


class DebateStrategy(TeamProcessStrategy):
    """多 Agent 辩论达成共识。

    每轮用 asyncio.gather 并行收集各 Agent 对当前 objective 的表态，
    轮间通过比较输出文本判断是否仍有分歧（无分歧则提前退出），
    最终由 CandidateEvaluationPipeline.evaluate 选出最优方案。

    复用 L1 的 CandidateEvaluationPipeline，
    验证"单 Agent 内部积木可直接复用为跨 Agent 编排能力"这一架构假设。
    """

    def __init__(
        self,
        evaluation_pipeline: CandidateEvaluationPipeline | None = None,
    ) -> None:
        self._pipeline = evaluation_pipeline

    async def run(self, context: TeamContext, objective: str) -> Result:
        if not context.members:
            return Result.failed("No members in team")

        max_rounds = (
            context.config.max_rounds
            if context.config and context.config.max_rounds
            else _DEFAULT_MAX_ROUNDS
        )

        current_objective = objective
        all_round_results: list[list[Result]] = []
        total_steps = 0

        for _round in range(max_rounds):
            tasks = [
                invoke_member(context, member, current_objective) for member in context.members
            ]
            round_results: list[Result] = await asyncio.gather(*tasks)
            total_steps += sum(r.total_steps for r in round_results)
            all_round_results.append(round_results)

            if self._has_consensus(round_results):
                return self._pick_first(round_results, total_steps)

            proposals = "\n".join(
                f"Agent {i}: {r.output or ''}" for i, r in enumerate(round_results)
            )
            current_objective = f"{objective}\n\nPrevious proposals:\n{proposals}"

        final_round = all_round_results[-1]
        result = await self._arbitrate(objective, final_round)
        result.total_steps = total_steps
        return result

    @staticmethod
    def _has_consensus(results: list[Result]) -> bool:
        """Check if all members produced identical output (no disagreement)."""
        if len(results) <= 1:
            return True
        outputs = {(r.output or "").strip() for r in results}
        return len(outputs) <= 1

    @staticmethod
    def _pick_first(results: list[Result], total_steps: int) -> Result:
        result = results[0] if results else Result.failed("No results")
        result.total_steps = total_steps
        return result

    async def _arbitrate(self, objective: str, results: list[Result]) -> Result:
        if not results:
            return Result.failed("No results to arbitrate")
        if self._pipeline is None or len(results) == 1:
            return results[0]
        state = AgentState(trace_id="debate", task=objective, budget=Budget())
        decisions = [
            Decision(
                decision_id=f"debate_{i}",
                action_type=ActionType.RESPOND,
                rationale=r.output or "",
                confidence=0.5,
                response_text=r.output,
            )
            for i, r in enumerate(results)
        ]
        winner = await self._pipeline.evaluate(state, decisions)
        for i, d in enumerate(decisions):
            if d.decision_id == winner.decision_id:
                return results[i]
        return results[0]
