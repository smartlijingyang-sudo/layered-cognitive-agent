"""HandoffStrategy — PEER: sequential try, first COMPLETED wins (no output chaining).

Distinct from ActionType.HANDOFF (non-blocking body action).
"""

from __future__ import annotations

from lca.contracts.protocols import TeamStage, TeamStrategy
from lca.contracts.result import Result
from lca.layer3_agent.member_invoke import invoke_members_sequential


class HandoffStrategy(TeamStrategy):
    """PEER topology: stop at the first member that completes."""

    def __init__(self, stage: TeamStage) -> None:
        self._stage = stage

    async def run(self, objective: str) -> Result:
        return await invoke_members_sequential(
            self._stage,
            objective,
            pass_output_as_next_task=False,
            stop_on_first_completed=True,
        )
