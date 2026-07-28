"""ParallelStrategy —— scatter-gather 并行执行 + Synthesizer 聚合。"""

from __future__ import annotations

import asyncio

from lca.contracts.protocols import (
    OrchestrationContext,
    OrchestrationStrategy,
    Synthesizer,
)
from lca.contracts.result import Result


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
            return Result.failed("No members in team")
        tasks = [member.execute(objective) for member in context.members]
        results: list[Result] = await asyncio.gather(*tasks)

        total_steps = sum(r.total_steps for r in results)

        if self._synthesizer is not None:
            synthesized = await self._synthesizer.synthesize(objective, results)
            synthesized.total_steps = total_steps
            return synthesized

        primary = results[-1]
        primary.total_steps = total_steps
        return primary
