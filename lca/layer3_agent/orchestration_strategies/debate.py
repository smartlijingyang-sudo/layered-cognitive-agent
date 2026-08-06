"""DebateStrategy — CHOREOGRAPHY: multi-round parallel until consensus or max rounds."""

from __future__ import annotations

import asyncio
import re

from lca.contracts.atoms.telemetry import ATTR_MAX_ROUNDS, ATTR_ROUND, SpanName
from lca.contracts.models.core.result import Result
from lca.contracts.protocols import Synthesizer, TeamStage, TeamStrategy
from lca.layer0_infra.observability import span

_NORMALIZE_RE = re.compile(r"\s+")


class DebateStrategy(TeamStrategy):
    """Multi-round parallel debate; exit early on consensus or max rounds."""

    def __init__(
        self,
        stage: TeamStage,
        max_rounds: int,
        synthesizer: Synthesizer | None = None,
    ) -> None:
        self._stage = stage
        self._max_rounds = max_rounds
        self._synthesizer = synthesizer

    async def run(self, objective: str) -> Result:
        members = self._stage.members
        if not members:
            return Result.failed("No members in team")
        current_objective = objective
        total_steps = 0

        for round_idx in range(self._max_rounds):
            with span(
                SpanName.TEAM_ROUND,
                **{ATTR_ROUND: round_idx, ATTR_MAX_ROUNDS: self._max_rounds},
            ):
                raw = await asyncio.gather(
                    *[self._stage.invoker.invoke(member, current_objective) for member in members],
                    return_exceptions=True,
                )
            round_results = [_to_result(r) for r in raw]
            total_steps += sum(r.total_steps for r in round_results)

            if _has_consensus(round_results):
                return _pick_first(round_results, total_steps)

            proposals = "\n".join(
                f"Agent {i}: {r.output or ''}" for i, r in enumerate(round_results)
            )
            current_objective = f"{objective}\n\nPrevious proposals:\n{proposals}"

        # 最终轮：仲裁
        result = await self._arbitrate(objective, round_results)
        result.total_steps = total_steps
        return result

    async def _arbitrate(self, objective: str, results: list[Result]) -> Result:
        if not results:
            return Result.failed("No results to arbitrate")
        if self._synthesizer is not None:
            return await self._synthesizer.synthesize(objective, results)
        return results[0]


def _to_result(raw: object) -> Result:
    if isinstance(raw, BaseException):
        return Result.failed(f"debate member error: {raw}")
    return raw  # type: ignore[return-value]


def _has_consensus(results: list[Result]) -> bool:
    """归一化共识检测：strip + lower + 合并连续空白。

    至少需要 2 个有效结果才能声明共识；单结果不构成辩论。
    """
    if len(results) < 2:
        return False
    normalized = {
        _NORMALIZE_RE.sub(" ", (r.output or "").strip().lower()) for r in results if r.output
    }
    return len(normalized) == 1


def _pick_first(results: list[Result], total_steps: int) -> Result:
    result = results[0] if results else Result.failed("No results")
    result.total_steps = total_steps
    return result
