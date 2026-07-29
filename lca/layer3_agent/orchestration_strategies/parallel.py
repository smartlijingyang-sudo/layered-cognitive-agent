"""ParallelStrategy."""

from __future__ import annotations

import asyncio

from lca.contracts.protocols import OrchestrationContext, OrchestrationStrategy, Synthesizer
from lca.contracts.result import Result
from lca.layer3_agent.member_invoke import invoke_member


class ParallelStrategy(OrchestrationStrategy):
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
