"""ParallelStrategy — CHOREOGRAPHY: concurrent members + optional synthesizer."""

from __future__ import annotations

import asyncio

from lca.contracts.budget import create_budget
from lca.contracts.lifecycle import TaskStatus
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
        raw = await asyncio.gather(
            *[self._stage.invoker.invoke(member, objective) for member in members],
            return_exceptions=True,
        )
        results = [_to_result(r) for r in raw]
        total_steps = sum(r.total_steps for r in results)

        if self._synthesizer is not None:
            ok_results = [r for r in results if r.status == TaskStatus.COMPLETED]
            if not ok_results:
                return Result.failed("All parallel members failed")
            with span(
                SpanName.TEAM_SYNTHESIS,
                **{
                    ATTR_CANDIDATE_COUNT: len(ok_results),
                    ATTR_SYNTHESIS_METHOD: type(self._synthesizer).__name__,
                },
            ):
                synthesized = await self._synthesizer.synthesize(objective, ok_results)
            synthesized.total_steps = total_steps
            return synthesized

        # 无 synthesizer：合并所有成功成员的输出
        ok_results = [r for r in results if r.status == TaskStatus.COMPLETED and r.output]
        if not ok_results:
            return Result.failed("All parallel members failed")
        if len(ok_results) == 1:
            out = ok_results[0]
            out.total_steps = total_steps
            return out
        budget = create_budget()
        budget.used_steps = total_steps
        return Result(
            trace_id=objective[:16],
            status=TaskStatus.COMPLETED,
            final_state_ref="",
            total_steps=total_steps,
            budget_used=budget,
            output="\n".join(str(r.output) for r in ok_results),
        )


def _to_result(raw: object) -> Result:
    """将 gather 结果（Result | BaseException）统一为 Result。"""
    if isinstance(raw, BaseException):
        return Result.failed(f"parallel member error: {raw}")
    return raw  # type: ignore[return-value]
