"""编排策略实现 —— hierarchical / sequential / parallel / graph(占位) / debate(占位)。"""

from __future__ import annotations

import asyncio
from typing import cast

from lca.contracts.protocols import OrchestrationContext, OrchestrationStrategy, Synthesizer
from lca.contracts.result import Result


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
    """基于 DAG 的自定义工作流（占位实现）。

    具体实现见后续子 PR，依赖 TransportRegistry 做跨节点通信。
    """

    async def run(self, context: OrchestrationContext, objective: str) -> Result:
        raise NotImplementedError("GraphStrategy 尚未实现，tracked in PR3a")


class DebateStrategy(OrchestrationStrategy):
    """多 Agent 辩论达成共识（占位实现）。

    具体实现见后续子 PR，将使用 asyncio.gather 多轮意见收集
    + 复用 L1 TaskCoordinator 仲裁。
    """

    async def run(self, context: OrchestrationContext, objective: str) -> Result:
        raise NotImplementedError("DebateStrategy 尚未实现，tracked in PR3b")
