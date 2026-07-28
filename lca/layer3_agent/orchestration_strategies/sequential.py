"""SequentialStrategy —— 任务像流水线一样在成员间顺序传递。"""

from __future__ import annotations

from lca.contracts.protocols import OrchestrationContext, OrchestrationStrategy
from lca.contracts.result import Result


class SequentialStrategy(OrchestrationStrategy):
    """任务像流水线一样在成员间顺序传递。"""

    async def run(self, context: OrchestrationContext, objective: str) -> Result:
        current_task = objective
        last_result: Result | None = None
        total_steps = 0
        for member in context.members:
            last_result = await member.execute(current_task)
            total_steps += last_result.total_steps
            if last_result.output:
                current_task = last_result.output
        if last_result is None:
            return Result.failed("No members in team")
        last_result.total_steps = total_steps
        return last_result
