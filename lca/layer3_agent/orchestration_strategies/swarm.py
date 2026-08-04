"""SwarmStrategy — PEER: round-robin peers with context accumulation."""

from __future__ import annotations

from lca.contracts.lifecycle import TaskStatus
from lca.contracts.protocols import TeamContext, TeamStrategy
from lca.contracts.result import Result
from lca.contracts.telemetry import ATTR_MAX_ROUNDS, ATTR_ROUND, SpanName
from lca.layer0_infra.observability import span
from lca.layer3_agent.member_invoke import invoke_member

_DEFAULT_SWARM_ROUNDS = 3


class SwarmStrategy(TeamStrategy):
    """Round-robin peers; accumulate peer updates until success or budget."""

    def __init__(self, max_rounds: int | None = None) -> None:
        self._max_rounds = max_rounds

    async def run(self, context: TeamContext, objective: str) -> Result:
        if not context.members:
            return Result.failed("No members in team")
        max_rounds = self._max_rounds
        if max_rounds is None and context.config is not None:
            max_rounds = context.config.max_rounds
        if max_rounds is None:
            max_rounds = _DEFAULT_SWARM_ROUNDS

        current = objective
        total_steps = 0
        last: Result | None = None
        for round_idx in range(max_rounds):
            with span(
                SpanName.TEAM_ROUND,
                **{ATTR_ROUND: round_idx, ATTR_MAX_ROUNDS: max_rounds},
            ):
                for member in context.members:
                    last = await invoke_member(context, member, current)
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
