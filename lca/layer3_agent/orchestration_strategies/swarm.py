"""SwarmStrategy — PEER: round-robin peers with context accumulation."""

from __future__ import annotations

from lca.contracts.atoms.telemetry import ATTR_MAX_ROUNDS, ATTR_ROUND, SpanName
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.result import Result
from lca.contracts.protocols import TeamStage, TeamStrategy
from lca.layer0_infra.observability import span


class SwarmStrategy(TeamStrategy):
    """Round-robin peers; accumulate peer updates until success or budget."""

    def __init__(self, stage: TeamStage, max_rounds: int) -> None:
        self._stage = stage
        self._max_rounds = max_rounds

    async def run(self, objective: str) -> Result:
        members = self._stage.members
        if not members:
            return Result.failed("No members in team")

        current = objective
        total_steps = 0
        last: Result | None = None
        for round_idx in range(self._max_rounds):
            with span(
                SpanName.TEAM_ROUND,
                **{ATTR_ROUND: round_idx, ATTR_MAX_ROUNDS: self._max_rounds},
            ):
                for member in members:
                    last = await self._stage.invoker.invoke(member, current)
                    total_steps += last.total_steps
                    if last.status == TaskStatus.COMPLETED and last.output:
                        last.total_steps = total_steps
                        return last
                    if last.output:
                        role = member.role_profile.role or "peer"
                        current = f"{objective}\n\nPeer update ({role}):\n{last.output}"
        if last is None:
            return Result.failed("No members in team")
        last.total_steps = total_steps
        return last
