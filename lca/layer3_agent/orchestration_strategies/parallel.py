"""ParallelStrategy — CHOREOGRAPHY: concurrent members + optional synthesizer."""

from __future__ import annotations

import asyncio

from lca.contracts.protocols import Synthesizer, TeamStage, TeamStrategy
from lca.contracts.result import Result
from lca.contracts.telemetry import ATTR_CANDIDATE_COUNT, ATTR_SYNTHESIS_METHOD, SpanName
from lca.layer0_infra.observability import span


class ParallelStrategy(TeamStrategy):
    """Run all members concurrently; optional Synthesizer aggregates results."""

    def __init__(self, stage: TeamStage, synthesizer: Synthesizer | None = None) -> None:
        self._stage = stage
        self._synthesizer = synthesizer

    async def run(self, objective: str) -> Result:
        members = self._stage.members
        if not members:
            return Result.failed("No members in team")
        results = await asyncio.gather(
            *[self._stage.invoker.invoke(member, objective) for member in members]
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
