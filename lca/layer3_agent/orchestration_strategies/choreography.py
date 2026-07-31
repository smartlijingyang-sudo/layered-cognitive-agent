"""ChoreographyStrategy — sequential / parallel / handoff / debate in one class.

Replaces 4 separate strategy classes with a single dispatch-table-driven
strategy. All four topologies are external choreography — they call members
directly via ``invoke_member`` without going through a supervisor's
cognitive loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from lca.contracts.protocols import Synthesizer, TeamContext, TeamProcessStrategy
from lca.contracts.result import Result
from lca.layer3_agent.member_invoke import invoke_member, invoke_members_sequential

_DEFAULT_MAX_ROUNDS = 3


class ChoreographyStrategy(TeamProcessStrategy):
    """External choreography with a topology dispatch table.

    Topologies:
    - ``sequential``: chain A → B → C, output passes to next member
    - ``parallel``: all members run concurrently, optional synthesizer aggregates
    - ``handoff``: sequential, first completed wins (no output chaining)
    - ``debate``: multi-round parallel, exits on consensus
    """

    def __init__(
        self,
        topology: str,
        synthesizer: Synthesizer | None = None,
        max_rounds: int | None = None,
    ) -> None:
        self._topology = topology
        self._synthesizer = synthesizer
        self._max_rounds = max_rounds

    async def run(self, context: TeamContext, objective: str) -> Result:
        runner = _DISPATCH.get(self._topology)
        if runner is None:
            raise ValueError(f"Unknown topology: {self._topology}")
        return await runner(self, context, objective)

    @staticmethod
    async def _run_sequential(
        _self: ChoreographyStrategy, context: TeamContext, objective: str
    ) -> Result:
        return await invoke_members_sequential(
            context, objective, pass_output_as_next_task=True, stop_on_first_completed=False
        )

    @staticmethod
    async def _run_handoff(
        _self: ChoreographyStrategy, context: TeamContext, objective: str
    ) -> Result:
        return await invoke_members_sequential(
            context, objective, pass_output_as_next_task=False, stop_on_first_completed=True
        )

    @staticmethod
    async def _run_parallel(
        self: ChoreographyStrategy, context: TeamContext, objective: str
    ) -> Result:
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

    @staticmethod
    async def _run_debate(
        self: ChoreographyStrategy, context: TeamContext, objective: str
    ) -> Result:
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

        for _round in range(max_rounds):
            round_results: list[Result] = await asyncio.gather(
                *[invoke_member(context, m, current_objective) for m in context.members]
            )
            total_steps += sum(r.total_steps for r in round_results)
            all_round_results.append(round_results)

            if _has_consensus(round_results):
                return _pick_first(round_results, total_steps)

            proposals = "\n".join(
                f"Agent {i}: {r.output or ''}" for i, r in enumerate(round_results)
            )
            current_objective = f"{objective}\n\nPrevious proposals:\n{proposals}"

        final_round = all_round_results[-1]
        result = await _arbitrate(self, objective, final_round)
        result.total_steps = total_steps
        return result


def _has_consensus(results: list[Result]) -> bool:
    if len(results) <= 1:
        return True
    outputs = {(r.output or "").strip() for r in results}
    return len(outputs) <= 1


def _pick_first(results: list[Result], total_steps: int) -> Result:
    result = results[0] if results else Result.failed("No results")
    result.total_steps = total_steps
    return result


async def _arbitrate(self: ChoreographyStrategy, objective: str, results: list[Result]) -> Result:
    if not results:
        return Result.failed("No results to arbitrate")
    if self._synthesizer is not None:
        return await self._synthesizer.synthesize(objective, results)
    return results[0]


_DISPATCH: dict[str, Callable[..., Awaitable[Result]]] = {
    "sequential": ChoreographyStrategy._run_sequential,
    "parallel": ChoreographyStrategy._run_parallel,
    "handoff": ChoreographyStrategy._run_handoff,
    "debate": ChoreographyStrategy._run_debate,
}
