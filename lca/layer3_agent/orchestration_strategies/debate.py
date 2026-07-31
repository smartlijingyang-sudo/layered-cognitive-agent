"""DebateStrategy —— 多 Agent 辩论达成共识。"""

from __future__ import annotations

import asyncio

from lca.contracts.protocols import (
    Synthesizer,
    TeamContext,
    TeamProcessStrategy,
)
from lca.contracts.result import Result
from lca.layer3_agent.member_invoke import invoke_member

_DEFAULT_MAX_ROUNDS = 3


class DebateStrategy(TeamProcessStrategy):
    """多 Agent 辩论达成共识。

    每轮用 asyncio.gather 并行收集各 Agent 对当前 objective 的表态，
    轮间通过比较输出文本判断是否仍有分歧（无分歧则提前退出），
    最终由 Synthesizer 汇总最优方案（无 Synthesizer 时取首个结果）。
    """

    def __init__(
        self,
        synthesizer: Synthesizer | None = None,
    ) -> None:
        self._synthesizer = synthesizer

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
        if self._synthesizer is not None:
            return await self._synthesizer.synthesize(objective, results)
        return results[0]
