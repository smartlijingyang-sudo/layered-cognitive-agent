"""ParallelStrategy —— 成员并行执行，可选合成器汇总结果。

L3 层职责：
    所有成员同时收到同一 objective 并行执行（asyncio.gather），
    执行完毕后：
    - 若有 Synthesizer，由其汇总所有结果为最终输出
    - 否则取最后一个成员的结果作为主输出
    总 step 数为所有成员 step 之和。
"""

from __future__ import annotations

import asyncio

from lca.contracts.protocols import OrchestrationContext, OrchestrationStrategy, Synthesizer
from lca.contracts.result import Result
from lca.layer3_agent.member_invoke import invoke_member


class ParallelStrategy(OrchestrationStrategy):
    """并行编排：所有成员同时执行同一任务，可选 Synthesizer 汇总结果。"""

    def __init__(self, synthesizer: Synthesizer | None = None) -> None:
        self._synthesizer = synthesizer

    async def run(self, context: OrchestrationContext, objective: str) -> Result:
        if not context.members:
            return Result.failed("No members in team")
        results = await asyncio.gather(
            *[invoke_member(context, m, objective) for m in context.members]
        )
        total_steps = sum(r.total_steps for r in results)
        if self._synthesizer is not None:
            synthesized = await self._synthesizer.synthesize(objective, list(results))
            synthesized.total_steps = total_steps
            return synthesized
        primary = results[-1]
        primary.total_steps = total_steps
        return primary
