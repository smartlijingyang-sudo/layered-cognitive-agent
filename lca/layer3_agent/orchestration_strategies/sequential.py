"""SequentialStrategy —— 任务像流水线一样在成员间顺序传递。"""

from __future__ import annotations

from lca.contracts.protocols import OrchestrationContext, OrchestrationStrategy
from lca.contracts.result import Result


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
