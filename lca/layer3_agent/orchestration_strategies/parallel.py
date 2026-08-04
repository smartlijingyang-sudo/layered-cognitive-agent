"""ParallelStrategy — CHOREOGRAPHY: concurrent members + optional synthesizer."""

from __future__ import annotations

import asyncio

from lca.contracts.protocols import Synthesizer, TeamContext, TeamStrategy
from lca.contracts.result import Result
from lca.contracts.telemetry import ATTR_CANDIDATE_COUNT, ATTR_SYNTHESIS_METHOD, SpanName
from lca.layer0_infra.observability import span
from lca.layer3_agent.member_invoke import invoke_member


class ParallelStrategy(TeamStrategy):
    """Run all members concurrently; optional Synthesizer aggregates results."""

    def __init__(self, synthesizer: Synthesizer | None = None) -> None:
        self._synthesizer = synthesizer

    async def run(self, context: TeamContext, objective: str) -> Result:
        if not context.members:
            return Result.failed("No members in team")
        results = await asyncio.gather(
            *[invoke_member(context, m, objective) for m in context.members]
        )
        total_steps = sum(r.total_steps for r in results)
        if self._synthesizer is not None:
            with span(
                SpanName.TEAM_SYNTHESIS,
                **{
                    ATTR_CANDIDATE_COUNT: len(results),
                    ATTR_SYNTHESIS_METHOD: type(self._synthesizer).__name__,
                },
            ):
                synthesized = await self._synthesizer.synthesize(objective, list(results))
            synthesized.total_steps = total_steps
            return synthesized
        primary = results[-1]
        primary.total_steps = total_steps
        return primary
