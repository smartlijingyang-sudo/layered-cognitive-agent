"""PEER-family strategies: handoff and swarm (ADR-0027).

Control transfers among members without a supervisor cognitive loop.
- handoff: sequential, first completed wins (no output chaining)
- swarm: round-robin peers with context accumulation until success or budget
"""

from __future__ import annotations

from lca.contracts.lifecycle import TaskStatus
from lca.contracts.protocols import TeamContext, TeamProcessStrategy
from lca.contracts.result import Result
from lca.layer3_agent.member_invoke import invoke_member, invoke_members_sequential

_DEFAULT_SWARM_ROUNDS = 3
_MODE_HANDOFF = "handoff"
_MODE_SWARM = "swarm"


class PeerStrategy(TeamProcessStrategy):
    """PEER family entry for handoff / swarm topologies."""

    def __init__(self, mode: str = _MODE_HANDOFF, max_rounds: int | None = None) -> None:
        if mode not in (_MODE_HANDOFF, _MODE_SWARM):
            raise ValueError(f"Unknown peer mode: {mode}")
        self._mode = mode
        self._max_rounds = max_rounds

    async def run(self, context: TeamContext, objective: str) -> Result:
        if self._mode == _MODE_HANDOFF:
            return await invoke_members_sequential(
                context,
                objective,
                pass_output_as_next_task=False,
                stop_on_first_completed=True,
            )
        return await self._run_swarm(context, objective)

    async def _run_swarm(self, context: TeamContext, objective: str) -> Result:
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
        for _round in range(max_rounds):
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
