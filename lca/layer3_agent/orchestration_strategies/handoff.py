"""HandoffStrategy —— 动态控制权移交，首个完成者胜出。"""

from __future__ import annotations

from lca.contracts.protocols import OrchestrationContext, OrchestrationStrategy
from lca.contracts.result import Result


class HandoffStrategy(OrchestrationStrategy):
    """动态控制权移交：按顺序将任务交给各 Agent，任一 Agent 完成即终止。

    与 SequentialStrategy 的区别：
    - Sequential：每个 Agent 都必须执行，像流水线一样传递
    - Handoff：第一个能完成任务的 Agent 执行后，后续 Agent 不再执行

    典型场景：客服分诊（分诊 Agent → 专家 Agent），不需要分诊 Agent 等结果。
    """

    async def run(self, context: OrchestrationContext, objective: str) -> Result:
        if not context.members:
            return Result.failed("No members in team")

        last_result: Result | None = None
        for member in context.members:
            result: Result = await member.execute(objective)
            last_result = result
            if result.status == "completed":
                return result

        return last_result or Result.failed("All members failed")
