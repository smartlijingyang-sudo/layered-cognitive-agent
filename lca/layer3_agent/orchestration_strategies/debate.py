"""DebateStrategy — CHOREOGRAPHY: multi-round parallel until consensus or max rounds."""

from __future__ import annotations

import asyncio

from lca.contracts.protocols import Synthesizer, TeamContext, TeamStrategy
from lca.contracts.result import Result
from lca.contracts.telemetry import ATTR_MAX_ROUNDS, ATTR_ROUND, SpanName
from lca.layer0_infra.observability import span
from lca.layer3_agent.member_invoke import invoke_member

_DEFAULT_MAX_ROUNDS = 3


class DebateStrategy(TeamStrategy):
    """Multi-round parallel debate; exit early on identical outputs."""

    def __init__(
        self,
        synthesizer: Synthesizer | None = None,
        max_rounds: int | None = None,
    ) -> None:
        self._synthesizer = synthesizer
        self._max_rounds = max_rounds

    async def run(self, context: TeamContext, objective: str) -> Result:
        if not context.members:
            return Result.failed("No members in team")
        max_rounds = self._max_rounds or (
            context.config.max_rounds
            if context.config and context.config.max_rounds
            else _DEFAULT_MAX_ROUNDS
        )
        current_objective = objective
        all_round_results: list[list[Result]] = []
        total_steps = 0

        for round_idx in range(max_rounds):
            with span(
                SpanName.TEAM_ROUND,
                **{ATTR_ROUND: round_idx, ATTR_MAX_ROUNDS: max_rounds},
            ):
                round_results = await asyncio.gather(
                    *[invoke_member(context, m, current_objective) for m in context.members]
                )
            total_steps += sum(r.total_steps for r in round_results)
            all_round_results.append(list(round_results))

            if _has_consensus(list(round_results)):
                return _pick_first(list(round_results), total_steps)

            proposals = "\n".join(
                f"Agent {i}: {r.output or ''}" for i, r in enumerate(round_results)
            )
            current_objective = f"{objective}\n\nPrevious proposals:\n{proposals}"

        final_round = all_round_results[-1]
        result = await self._arbitrate(objective, final_round)
        result.total_steps = total_steps
        return result

    async def _arbitrate(self, objective: str, results: list[Result]) -> Result:
        if not results:
            return Result.failed("No results to arbitrate")
        if self._synthesizer is not None:
            return await self._synthesizer.synthesize(objective, results)
        return results[0]


def _has_consensus(results: list[Result]) -> bool:
    if len(results) <= 1:
        return True
    return len({(r.output or "").strip() for r in results}) <= 1


def _pick_first(results: list[Result], total_steps: int) -> Result:
    result = results[0] if results else Result.failed("No results")
    result.total_steps = total_steps
    return result
